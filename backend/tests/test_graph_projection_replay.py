from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app import models
from app.cruds import graph_projection as graph_projection_crud
from app.services import social_event_runtime
from app.services.graph_projection_commands import (
    RelationshipStateProjectionCommand,
    SourceExclusionProjectionCommand,
)

from app.services.graph_projection_replay import (
    GraphProjectionReplayService,
    GraphReplayError,
    create_replay_run,
    projection_digest,
)
from p7_graph_support import seed_projection_fixture, sqlite_engine


class ReplayStore:
    def __init__(self) -> None:
        self.cleared_worlds: list[str] = []
        self.commands = []

    def clear_world(self, world_id: str) -> None:
        self.cleared_worlds.append(world_id)

    def apply(self, command, *, timeout_seconds: float = 5.0) -> str:
        self.commands.append(command)
        return "applied"

    def world_digest(self, world_id: str) -> dict[str, list[str]]:
        return projection_digest(self.commands)


def test_world_rebuild_records_audit_and_replays_high_water_set() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db)
        run = create_replay_run(
            db,
            world_id=fixture.world.id,
            mode="world_rebuild",
            source_event_id=None,
            requested_by="local-maintainer",
            reason_code="p7_fixture_rebuild",
        )
        run_id = run.id
        db.commit()
    store = ReplayStore()
    service = GraphProjectionReplayService(
        session_factory=lambda: Session(engine, expire_on_commit=False),
        store=store,
        worker_id="replay-worker",
    )
    completed = service.execute(run_id)
    assert completed.status == "succeeded"
    assert completed.total_count == 1
    assert completed.applied_count == 1
    assert completed.high_water_outbox_id is not None
    assert store.cleared_worlds == [fixture.world.id]
    assert len(store.commands) == 1
    with Session(engine) as db:
        counts = graph_projection_crud.world_counts(db, world_id=fixture.world.id)
        assert not counts.failed_rebuild


def test_world_rebuild_preserves_relationship_when_source_is_hidden() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="hidden-rebuild")
        changed = social_event_runtime.exclude_events_for_posts(
            db,
            post_ids=[fixture.reply_post.id],
            reason="source_hidden",
            invalidated_at=datetime(2026, 8, 12, 2, 0, tzinfo=UTC),
        )
        assert changed == 1
        run = create_replay_run(
            db,
            world_id=fixture.world.id,
            mode="world_rebuild",
            source_event_id=None,
            requested_by="local-maintainer",
            reason_code="verify_hidden_relationship_rebuild",
        )
        run_id = run.id
        db.commit()

    store = ReplayStore()
    completed = GraphProjectionReplayService(
        session_factory=lambda: Session(engine, expire_on_commit=False),
        store=store,
        worker_id="replay-worker",
    ).execute(run_id)

    assert completed.status == "succeeded"
    assert completed.total_count == 2
    assert completed.applied_count == 2
    assert [type(command) for command in store.commands] == [
        RelationshipStateProjectionCommand,
        SourceExclusionProjectionCommand,
    ]
    digest = store.world_digest(fixture.world.id)
    assert len(digest["world_characters"]) == 2
    assert len(digest["events"]) == 0
    assert len(digest["relationships"]) == 1
    assert len(digest["evidence"]) == 0


def test_event_reprocess_does_not_clear_world() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="event")
        run = create_replay_run(
            db,
            world_id=fixture.world.id,
            mode="event_reprocess",
            source_event_id=fixture.event.id,
            requested_by="local-maintainer",
            reason_code="repair_single_event",
        )
        run_id = run.id
        db.commit()
    store = ReplayStore()
    completed = GraphProjectionReplayService(
        session_factory=lambda: Session(engine, expire_on_commit=False),
        store=store,
        worker_id="replay-worker",
    ).execute(run_id)
    assert completed.status == "succeeded"
    assert store.cleared_worlds == []
    assert len(store.commands) == 1


def test_world_rebuild_fails_closed_when_graph_parity_mismatches() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="parity")
        run = create_replay_run(
            db,
            world_id=fixture.world.id,
            mode="world_rebuild",
            source_event_id=None,
            requested_by="local-maintainer",
            reason_code="verify_parity_failure",
        )
        run_id = run.id
        db.commit()

    class MismatchedStore(ReplayStore):
        def world_digest(self, world_id: str) -> dict[str, list[str]]:
            return {
                "world_characters": [],
                "events": [],
                "relationships": [],
                "evidence": [],
            }

    try:
        GraphProjectionReplayService(
            session_factory=lambda: Session(engine, expire_on_commit=False),
            store=MismatchedStore(),
            worker_id="replay-worker",
        ).execute(run_id)
    except GraphReplayError as exc:
        assert exc.error_class == "replay_parity_mismatch"
    else:
        raise AssertionError("replay parity mismatch must fail closed")

    with Session(engine) as db:
        failed = db.get(models.GraphProjectionReplayRun, run_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.last_error_class == "replay_parity_mismatch"
        counts = graph_projection_crud.world_counts(db, world_id=fixture.world.id)
        assert counts.failed_rebuild
        assert not counts.active_replay

def test_world_rebuild_resume_keeps_original_high_water_and_leaves_delta_tail() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="resume")
        run = create_replay_run(
            db,
            world_id=fixture.world.id,
            mode="world_rebuild",
            source_event_id=None,
            requested_by="local-maintainer",
            reason_code="verify_resume_high_water",
        )
        run_id = run.id
        db.commit()

    first_service = GraphProjectionReplayService(
        session_factory=lambda: Session(engine, expire_on_commit=False),
        store=ReplayStore(),
        worker_id="replay-worker-a",
    )
    _, _, _, first_ids = first_service._start(run_id)
    assert first_ids == [fixture.outbox.id]

    with Session(engine, expire_on_commit=False) as db:
        persisted = db.get(models.GraphProjectionReplayRun, run_id)
        assert persisted is not None
        original_created_at = persisted.high_water_created_at
        original_outbox_id = persisted.high_water_outbox_id
        persisted.lease_expires_at = None
        db.add(
            models.GraphProjectionOutbox(
                id="p7-resume-delta-outbox",
                world_id=fixture.world.id,
                source_event_id=fixture.event.id,
                projection_type="source_exclusion",
                payload_version="source-exclusion-v1",
                payload={"event_id": fixture.event.id},
                source_signature="d" * 64,
                dedupe_key="p7-resume-delta-dedupe",
                status="pending",
                created_at=fixture.outbox.created_at + timedelta(seconds=1),
            )
        )
        db.commit()

    resumed_service = GraphProjectionReplayService(
        session_factory=lambda: Session(engine, expire_on_commit=False),
        store=ReplayStore(),
        worker_id="replay-worker-b",
    )
    _, _, _, resumed_ids = resumed_service._start(run_id)
    assert resumed_ids == first_ids

    with Session(engine) as db:
        resumed = db.get(models.GraphProjectionReplayRun, run_id)
        assert resumed is not None
        assert resumed.high_water_created_at == original_created_at
        assert resumed.high_water_outbox_id == original_outbox_id
        assert resumed.total_count == 1
        assert resumed.lease_owner == "replay-worker-b"

def test_graph_readiness_is_rebuilding_only_for_world_rebuild() -> None:
    event_engine = sqlite_engine()
    with Session(event_engine, expire_on_commit=False) as db:
        event_fixture = seed_projection_fixture(db, suffix="event-readiness")
        create_replay_run(
            db,
            world_id=event_fixture.world.id,
            mode="event_reprocess",
            source_event_id=event_fixture.event.id,
            requested_by="local-maintainer",
            reason_code="verify_event_reprocess_readiness",
        )
        db.commit()
        assert not graph_projection_crud.world_counts(
            db, world_id=event_fixture.world.id
        ).active_replay

    rebuild_engine = sqlite_engine()
    with Session(rebuild_engine, expire_on_commit=False) as db:
        rebuild_fixture = seed_projection_fixture(db, suffix="rebuild-readiness")
        create_replay_run(
            db,
            world_id=rebuild_fixture.world.id,
            mode="world_rebuild",
            source_event_id=None,
            requested_by="local-maintainer",
            reason_code="verify_world_rebuild_readiness",
        )
        db.commit()
        assert graph_projection_crud.world_counts(
            db, world_id=rebuild_fixture.world.id
        ).active_replay
