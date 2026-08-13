from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services import social_event_runtime
from app.services.graph_projection_commands import (
    ProjectionCommandError,
    RelationshipStateProjectionCommand,
    SourceExclusionProjectionCommand,
    build_projection_command,
)
from p7_graph_support import seed_projection_fixture, sqlite_engine


def _signature(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def test_rehydrates_relationship_snapshot_from_postgres() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db)
        command = build_projection_command(db, outbox_id=fixture.outbox.id)

    assert isinstance(command, RelationshipStateProjectionCommand)
    assert command.event.world_id == fixture.world.id
    assert command.event.actor_world_character_id == fixture.actor_world_character.id
    assert command.event.target_world_character_id == fixture.target_world_character.id
    assert command.relationship_state_id == fixture.relationship.id
    assert command.relationship_version == fixture.relationship.version
    assert command.interaction_count == fixture.relationship.interaction_count


@pytest.mark.parametrize(
    ("mutation", "error_class"),
    [
        ("signature", "signature_mismatch"),
        ("version", "payload_version_unsupported"),
        ("extra_key", "payload_invalid"),
        ("world", "world_mismatch"),
    ],
)
def test_rejects_untrusted_outbox_before_graph_call(
    mutation: str, error_class: str
) -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix=mutation)
        row = db.get(models.GraphProjectionOutbox, fixture.outbox.id)
        assert row is not None
        if mutation == "signature":
            row.source_signature = "0" * 64
        elif mutation == "version":
            row.payload_version = "future-v99"
        elif mutation == "extra_key":
            row.payload = {**row.payload, "unexpected": "value"}
            row.source_signature = _signature(row.payload)
        else:
            row.payload = {**row.payload, "world_id": "another-world"}
            row.source_signature = _signature(row.payload)
        db.commit()
        with pytest.raises(ProjectionCommandError) as exc_info:
            build_projection_command(db, outbox_id=row.id)
    assert exc_info.value.error_class == error_class


def test_source_exclusion_command_keeps_postgres_audit_event() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="excluded")
        changed = social_event_runtime.exclude_events_for_posts(
            db,
            post_ids=[fixture.reply_post.id],
            reason="source_hidden",
            invalidated_at=datetime(2026, 8, 12, 2, 0, tzinfo=UTC),
        )
        db.commit()
        exclusion = db.scalar(
            select(models.GraphProjectionOutbox).where(
                models.GraphProjectionOutbox.source_event_id == fixture.event.id,
                models.GraphProjectionOutbox.projection_type == "source_exclusion",
            )
        )
        assert exclusion is not None
        command = build_projection_command(db, outbox_id=exclusion.id)
        event = db.get(models.SocialEvent, fixture.event.id)

    assert changed == 1
    assert isinstance(command, SourceExclusionProjectionCommand)
    assert command.reason == "source_hidden"
    assert event is not None
    assert event.retrieval_status == "excluded"


def test_world_replay_restores_relationship_before_source_exclusion() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="replay-excluded")
        social_event_runtime.exclude_events_for_posts(
            db,
            post_ids=[fixture.reply_post.id],
            reason="source_hidden",
            invalidated_at=datetime(2026, 8, 12, 2, 0, tzinfo=UTC),
        )
        db.commit()
        exclusion = db.scalar(
            select(models.GraphProjectionOutbox).where(
                models.GraphProjectionOutbox.source_event_id == fixture.event.id,
                models.GraphProjectionOutbox.projection_type == "source_exclusion",
            )
        )
        assert exclusion is not None

        worker_command = build_projection_command(
            db, outbox_id=fixture.outbox.id
        )
        replay_relationship = build_projection_command(
            db,
            outbox_id=fixture.outbox.id,
            replay_relationship_snapshot=True,
        )
        replay_exclusion = build_projection_command(
            db,
            outbox_id=exclusion.id,
            replay_relationship_snapshot=True,
        )

    assert isinstance(worker_command, SourceExclusionProjectionCommand)
    assert isinstance(replay_relationship, RelationshipStateProjectionCommand)
    assert replay_relationship.relationship_state_id == fixture.relationship.id
    assert replay_relationship.relationship_version == fixture.relationship.version
    assert isinstance(replay_exclusion, SourceExclusionProjectionCommand)
