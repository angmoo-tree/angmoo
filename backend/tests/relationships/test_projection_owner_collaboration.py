from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app import models
from app.domains.relationships.contracts.projection_commands import (
    ProjectionCommandError,
    RelationshipStateProjectionCommand,
    SourceExclusionProjectionCommand,
)
from app.domains.world_characters.service import projection_scope
from app.runtime.graph_projection import command_references
from app.runtime.graph_projection.sqlalchemy_commands import build_projection_command
from p7_graph_support import seed_projection_fixture, sqlite_engine


def test_projection_reads_same_session_sources_and_historical_inactive_membership(monkeypatch):
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="projection-owner")
        membership = db.get(models.WorldMembership, fixture.actor_world_character.membership_id)
        fixture.actor_world_character.status = "left"
        membership.status = "left"
        calls = []
        original = command_references.get_projection_world_character

        def read_scope(session, **kwargs):
            assert session is db
            row = original(session, **kwargs)
            calls.append(row)
            return row

        monkeypatch.setattr(command_references, "get_projection_world_character", read_scope)
        command = build_projection_command(db, outbox_id=fixture.outbox.id)
        assert isinstance(command, RelationshipStateProjectionCommand)
        assert calls == [
            fixture.actor_world_character,
            fixture.target_world_character,
            fixture.actor_world_character,
            fixture.target_world_character,
        ]

        fixture.reply_post.report_hidden_at = datetime(2026, 9, 6, tzinfo=UTC)
        calls.clear()
        hidden = build_projection_command(db, outbox_id=fixture.outbox.id)
        assert isinstance(hidden, SourceExclusionProjectionCommand)
        assert hidden.reason == "source_hidden"
        assert calls == []
        assert fixture.event.retrieval_status == "eligible"
        db.rollback()
        assert fixture.actor_world_character.status == "active"
        assert membership.status == "active"
        assert fixture.reply_post.report_hidden_at is None
    engine.dispose()


@pytest.mark.parametrize("missing", [False, True])
def test_projection_scope_rejects_misrouted_membership_before_target_read(monkeypatch, missing):
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="expected-projection-owner")
        other = seed_projection_fixture(db, suffix="other-projection-owner")
        foreign_membership = db.get(models.WorldMembership, other.actor_world_character.membership_id)
        calls = []

        def misrouted_read(session, membership_id):
            assert session is db
            calls.append(membership_id)
            return None if missing else foreign_membership

        monkeypatch.setattr(projection_scope, "get_character_entry_membership", misrouted_read)
        with pytest.raises(ProjectionCommandError) as error:
            build_projection_command(db, outbox_id=fixture.outbox.id)
        assert error.value.error_class == "world_mismatch"
        assert error.value.terminal is True
        assert error.value.cancelled is False
        assert calls == [fixture.actor_world_character.membership_id]
        assert fixture.outbox.status == "pending"
    engine.dispose()
