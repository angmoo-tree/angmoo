from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app import models
from app.domains.relationships.projection.commands import (
    NoGraphMutationCommand,
    RelationshipStateProjectionCommand,
    SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)
from app.integrations.ladybug_projection import (
    LadybugProjectionError,
    LadybugRelationshipProjection,
)
from app.services.graph_projection_worker import GraphProjectionWorker
from p7_graph_support import seed_projection_fixture, sqlite_engine


NOW = datetime(2026, 8, 20, 1, 2, 3, tzinfo=UTC)


def _event(
    *,
    world_id: str = "world-arcana",
    event_id: str = "event-comment-1",
    actor_id: str = "wc-mango",
    target_id: str | None = "wc-sage",
) -> SocialEventProjectionCommand:
    return SocialEventProjectionCommand(
        world_id=world_id,
        event_id=event_id,
        event_type="reply_created",
        occurred_at=NOW,
        schema_version="social-event-v1",
        actor_world_character_id=actor_id,
        actor_character_id="char-mango",
        target_world_character_id=target_id,
        target_character_id="char-sage" if target_id else None,
    )


def _relationship(
    *, event: SocialEventProjectionCommand | None = None, version: int = 1
) -> RelationshipStateProjectionCommand:
    source = event or _event()
    return RelationshipStateProjectionCommand(
        event=source,
        relationship_state_id=f"relationship-{source.world_id}",
        familiarity=12 + version,
        affinity=7 + version,
        trust=5 + version,
        tension=version,
        interaction_count=3 + version,
        last_event_id=source.event_id,
        last_event_at=source.occurred_at,
        updated_at=source.occurred_at,
        relationship_version=version,
    )


def _root(tmp_path: Path) -> Path:
    return tmp_path / "한글 사용자" / "Angmoo graph"


def test_schema_projection_is_idempotent_and_reopens(tmp_path: Path) -> None:
    root = _root(tmp_path)
    command = _relationship(version=2)

    with LadybugRelationshipProjection(database_root=root) as projection:
        projection.verify_connectivity()
        assert projection.apply(command) == "applied"
        assert projection.apply(command) == "applied"
        first_digest = projection.world_digest(command.event.world_id)

    with LadybugRelationshipProjection(database_root=root) as reopened:
        assert reopened.world_digest(command.event.world_id) == first_digest

    assert first_digest == {
        "world_characters": ['["wc-mango"]', '["wc-sage"]'],
        "events": ['["event-comment-1"]'],
        "relationships": [
            '["relationship-world-arcana","wc-mango","wc-sage",2,14,9,7,2,5]'
        ],
        "evidence": [
            '["relationship-world-arcana","wc-mango","wc-sage",'
            '"event-comment-1",2]'
        ],
    }


def test_event_without_target_projects_only_actor_and_source(tmp_path: Path) -> None:
    event = _event(event_id="event-post-1", target_id=None)
    with LadybugRelationshipProjection(database_root=_root(tmp_path)) as projection:
        assert projection.apply(event) == "applied"
        assert projection.apply(event) == "applied"
        digest = projection.world_digest(event.world_id)

    assert digest == {
        "world_characters": ['["wc-mango"]'],
        "events": ['["event-post-1"]'],
        "relationships": [],
        "evidence": [],
    }


def test_stale_version_does_not_replace_relationship_state(tmp_path: Path) -> None:
    with LadybugRelationshipProjection(database_root=_root(tmp_path)) as projection:
        current = _relationship(version=3)
        stale = replace(
            _relationship(version=2),
            familiarity=99,
            affinity=99,
        )

        assert projection.apply(current) == "applied"
        assert projection.apply(stale) == "stale_noop"
        digest = projection.world_digest(current.event.world_id)

    assert digest["relationships"] == [
        '["relationship-world-arcana","wc-mango","wc-sage",3,15,10,8,3,6]'
    ]


def test_source_exclusion_is_idempotent_and_removes_only_evidence(
    tmp_path: Path,
) -> None:
    command = _relationship()
    exclusion = SourceExclusionProjectionCommand(
        world_id=command.event.world_id,
        event_id=command.event.event_id,
        reason="source_hidden",
    )
    with LadybugRelationshipProjection(database_root=_root(tmp_path)) as projection:
        assert projection.apply(command) == "applied"
        assert projection.apply(exclusion) == "removed"
        assert projection.apply(exclusion) == "noop"
        digest = projection.world_digest(command.event.world_id)

    assert digest["events"] == []
    assert digest["evidence"] == []
    assert len(digest["relationships"]) == 1


def test_world_scope_clear_and_noop_do_not_cross_worlds(tmp_path: Path) -> None:
    arcana = _relationship()
    other_event = _event(
        world_id="world-other",
        event_id="event-other-1",
        actor_id="wc-other-mango",
        target_id="wc-other-sage",
    )
    other = _relationship(event=other_event)
    with LadybugRelationshipProjection(database_root=_root(tmp_path)) as projection:
        assert projection.apply(arcana) == "applied"
        assert projection.apply(other) == "applied"
        assert (
            projection.apply(
                NoGraphMutationCommand(
                    world_id=arcana.event.world_id,
                    event_id="noop-1",
                    reason="unsupported_event",
                )
            )
            == "noop"
        )
        projection.clear_world(arcana.event.world_id)

        assert projection.world_digest(arcana.event.world_id) == {
            "world_characters": [],
            "events": [],
            "relationships": [],
            "evidence": [],
        }
        assert len(projection.world_digest(other.event.world_id)["relationships"]) == 1


def test_second_read_write_owner_is_rejected_and_lock_is_released(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    first = LadybugRelationshipProjection(database_root=root)
    try:
        with pytest.raises(LadybugProjectionError) as exc_info:
            LadybugRelationshipProjection(database_root=root)
        assert exc_info.value.error_class == "ladybug_writer_lock_unavailable"
    finally:
        first.close()

    with LadybugRelationshipProjection(database_root=root) as reopened:
        reopened.verify_connectivity()


class _UnavailableLadybugProjection:
    def apply(self, command, *, timeout_seconds: float = 5.0) -> str:
        raise LadybugProjectionError("ladybug_unavailable")


def test_ladybug_outage_keeps_sqlite_outbox_pending() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="ladybug-outage")
        outbox_id = fixture.outbox.id

    result = GraphProjectionWorker(
        session_factory=lambda: Session(engine, expire_on_commit=False),
        store=_UnavailableLadybugProjection(),
        worker_id="ladybug-worker",
    ).process_batch()

    with Session(engine) as db:
        row = db.get(models.GraphProjectionOutbox, outbox_id)
        assert row is not None
        assert row.status == "pending"
        assert row.last_error_class == "ladybug_unavailable"
        assert row.lease_owner is None
    assert result.retried == 1
    assert result.graph_degraded is True
