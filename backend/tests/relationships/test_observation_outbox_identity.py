"""Observer-specific outbox identity and caller-owned persistence boundaries."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.relationships import models
from app.domains.relationships.exceptions import ObservationOutboxIntegrityError
from app.domains.relationships.repository import events as event_queries
from app.runtime.social.observations import observe_source
from p7_graph_support import seed_projection_fixture, sqlite_engine


def _observe(db: Session, *, suffix: str):
    fixture = seed_projection_fixture(db, suffix=suffix)
    result = observe_source(
        db, world_id=fixture.world.id,
        observer_world_character_id=fixture.target_world_character.id,
        source_social_event_id=fixture.event.id,
        source_post_id=fixture.reply_post.id,
        lane="feed", observed_at=datetime(2026, 9, 24, tzinfo=UTC),
    )
    db.commit()
    row = db.scalar(select(models.GraphProjectionOutbox).where(
        models.GraphProjectionOutbox.payload_version == "relationship-observation-v1"
    ))
    assert row is not None
    return fixture, result, row


@pytest.mark.parametrize("status", ["pending", "processing", "succeeded", "dead", "cancelled"])
def test_replay_keeps_existing_outbox_lifecycle(status: str) -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture, original, row = _observe(db, suffix=f"lifecycle-{status}")
        row.status = status
        row.attempt_count = 3
        row.lease_owner = "worker-test"
        row.last_error_class = "past_failure"
        db.commit()
        before = (row.id, row.status, row.attempt_count, row.lease_owner,
                  row.last_error_class, row.created_at, row.updated_at)
        replay = observe_source(
            db, world_id=fixture.world.id,
            observer_world_character_id=fixture.target_world_character.id,
            source_social_event_id=fixture.event.id,
            source_post_id=fixture.reply_post.id,
            lane="routine", observed_at=datetime(2026, 9, 24, tzinfo=UTC),
        )
        db.commit()
        db.refresh(row)
        assert replay.replayed is True and replay.receipt_id == original.receipt_id
        assert before == (row.id, row.status, row.attempt_count, row.lease_owner,
                          row.last_error_class, row.created_at, row.updated_at)


def test_observation_natural_key_and_required_columns() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture, _, row = _observe(db, suffix="constraints")
        base = dict(
            world_id=fixture.world.id,
            source_event_id=fixture.event.id,
            relationship_state_id=row.relationship_state_id,
            projection_type=row.projection_type,
            payload_version=row.payload_version,
            payload=row.payload,
            source_signature=row.source_signature,
            status="pending", attempt_count=0,
        )
        for suffix, overrides in (
            ("natural", {}),
            ("missing-source", {"source_event_id": None}),
            ("missing-state", {"relationship_state_id": None}),
        ):
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.add(models.GraphProjectionOutbox(
                        id=f"bad-observation-{suffix}",
                        dedupe_key=f"bad-observation-{suffix}",
                        **{**base, **overrides},
                    ))
                    db.flush()
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 2


def test_other_event_uniqueness_and_snapshot_null_source_are_preserved() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="other-keys")
        original = fixture.outbox
        for relationship_state_id in (None, fixture.relationship.id):
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.add(models.GraphProjectionOutbox(
                        id=f"duplicate-regular-{relationship_state_id or 'null'}",
                        world_id=fixture.world.id, source_event_id=fixture.event.id,
                        relationship_state_id=relationship_state_id,
                        projection_type=original.projection_type,
                        payload_version=original.payload_version,
                        payload=original.payload, source_signature=original.source_signature,
                        dedupe_key=f"duplicate-regular-{relationship_state_id or 'null'}",
                        status="pending", attempt_count=0,
                    ))
                    db.flush()
        for version in ("relationship-snapshot-v1", "relationship-snapshot-v2"):
            db.add(models.GraphProjectionOutbox(
                id=f"snapshot-{version}", world_id=fixture.world.id,
                source_event_id=None, relationship_state_id=fixture.relationship.id,
                projection_type="relationship_snapshot", payload_version=version,
                payload={"world_id": fixture.world.id,
                         "relationship_state_id": fixture.relationship.id,
                         "relationship_version": fixture.relationship.version},
                source_signature="0" * 64, dedupe_key=f"snapshot-{version}",
                status="pending", attempt_count=0,
            ))
        db.commit()
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 3


def test_replay_restores_missing_outbox_without_reapplying_receipt() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture, original, row = _observe(db, suffix="missing-outbox")
        state = db.get(models.RelationshipState, original.relationship_state_id)
        assert state is not None
        before = (state.version, state.interaction_count, state.familiarity)
        old_id = row.id
        db.delete(row)
        db.commit()
        replay = observe_source(
            db, world_id=fixture.world.id,
            observer_world_character_id=fixture.target_world_character.id,
            source_social_event_id=fixture.event.id,
            source_post_id=fixture.reply_post.id,
            lane="inbox", observed_at=datetime(2026, 9, 24, tzinfo=UTC),
        )
        db.commit()
        assert replay.replayed is True
        assert replay.receipt_id == original.receipt_id
        assert (state.version, state.interaction_count, state.familiarity) == before
        replacement = db.scalar(select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.payload_version == "relationship-observation-v1"
        ))
        assert replacement is not None and replacement.id != old_id
        assert replacement.relationship_state_id == state.id


def test_changed_payload_is_never_reused_as_a_valid_observation() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture, _, row = _observe(db, suffix="tampered")
        row.payload = {**row.payload, "target_world_character_id": "wrong-target"}
        db.commit()
        with pytest.raises(ObservationOutboxIntegrityError, match="observation_outbox_payload_mismatch"):
            observe_source(
                db, world_id=fixture.world.id,
                observer_world_character_id=fixture.target_world_character.id,
                source_social_event_id=fixture.event.id,
                source_post_id=fixture.reply_post.id,
                lane="feed", observed_at=datetime(2026, 9, 24, tzinfo=UTC),
            )
        db.rollback()
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 2


def test_repository_only_suppresses_matching_dedupe_conflict() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture, _, row = _observe(db, suffix="repository-conflict")
        values = {
            "id": "new-repository-observation",
            "world_id": fixture.world.id,
            "source_event_id": fixture.event.id,
            "relationship_state_id": row.relationship_state_id,
            "projection_type": row.projection_type,
            "payload_version": row.payload_version,
            "payload": row.payload,
            "source_signature": row.source_signature,
            "dedupe_key": row.dedupe_key,
            "status": "pending",
            "attempt_count": 0,
        }
        reused = event_queries.insert_observation_outbox_if_absent(db, values=values)
        assert reused.id == row.id
        assert reused.id != values["id"]
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                event_queries.insert_observation_outbox_if_absent(
                    db, values={**values, "dedupe_key": "unrelated-natural-key"}
                )
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 2


def test_outbox_insert_failure_rolls_back_flushed_state_and_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="insert-failure")

        def reject_insert(*_args, **_kwargs):
            raise RuntimeError("injected_outbox_insert_failure")

        with monkeypatch.context() as patch:
            patch.setattr(event_queries, "insert_observation_outbox_if_absent", reject_insert)
            with pytest.raises(RuntimeError, match="injected_outbox_insert_failure"):
                observe_source(
                    db, world_id=fixture.world.id,
                    observer_world_character_id=fixture.target_world_character.id,
                    source_social_event_id=fixture.event.id,
                    source_post_id=fixture.reply_post.id,
                    lane="feed", observed_at=datetime(2026, 9, 24, tzinfo=UTC),
                )
            db.rollback()
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 1
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 1
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 1


def test_observation_writes_rollback_with_caller_transaction() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="rollback")
        observe_source(
            db, world_id=fixture.world.id,
            observer_world_character_id=fixture.target_world_character.id,
            source_social_event_id=fixture.event.id,
            source_post_id=fixture.reply_post.id,
            lane="feed", observed_at=datetime(2026, 9, 24, tzinfo=UTC),
        )
        db.rollback()
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 1
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 1
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 1
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 1
