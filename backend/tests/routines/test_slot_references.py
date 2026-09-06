from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, object_session

from app.domains.routines.models import AgentSlot
from app.domains.routines.service import slot_assignments
from app.runtime.resident import slots
from app.runtime.resident.slot_references import SqlAlchemySlotReferences
from routine_posts.test_runtime import _seed
from routines.test_activity_persistence import _file_engine


@pytest.mark.parametrize("commit", (False, True))
def test_character_lock_uses_caller_session_after_slot_pool_write(tmp_path, commit):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        character_id = fixture.character.id
        original_name = fixture.character.name
        fixture.character.name = "pending during slot assignment"
        lock_observations = []

        class ObservedReferences(SqlAlchemySlotReferences):
            def lock_character_id(self, requested_id):
                assert self.db is db
                assert requested_id == character_id
                with Session(engine) as observer:
                    saved = observer.get(AgentSlot, "same-session-slot")
                    lock_observations.append(saved is not None)
                    assert (saved is not None) is commit
                    if saved is not None:
                        assert saved.assigned_character_id is None
                return super().lock_character_id(requested_id)

        references = ObservedReferences(db)
        assert references.get_character(character_id) is fixture.character
        assigned = slot_assignments.assign_resident_slot(
            db,
            agent_ids=["same-session-slot"],
            user_id=fixture.user.id,
            character_id=character_id,
            credential_id=fixture.credential.id,
            heartbeat_interval_seconds=60,
            next_tick_at=datetime(2026, 9, 6, tzinfo=UTC),
            commit=commit,
            references=references,
        )
        assert lock_observations == [commit]
        assert assigned is not None
        assert object_session(assigned) is db
        assert assigned.assigned_character_id == character_id
        with Session(engine) as observer:
            saved = observer.get(AgentSlot, "same-session-slot")
            assert (saved is not None) is commit
            if saved is not None:
                assert saved.assigned_character_id == character_id
        db.rollback()
        saved = db.get(AgentSlot, "same-session-slot")
        assert (saved is not None) is commit
        assert fixture.character.name == (
            "pending during slot assignment" if commit else original_name
        )
    engine.dispose()


def test_empty_slot_scope_returns_before_queries_or_transactions(tmp_path):
    engine = _file_engine(tmp_path)
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def statement(_connection, _cursor, text, _parameters, _context, _many):
        statements.append(text)

    with Session(engine) as db:
        references = SqlAlchemySlotReferences(db)
        assert references.db is db
        assert slots.claim_due_resident_slots(
            db, now=datetime(2026, 9, 6, tzinfo=UTC), max_count=2,
            lease_seconds=60, allowed_character_ids=set(), single_flight=True,
        ) == []
        assert slots.assign_resident_slot(
            db, agent_ids=[], user_id="unused", character_id="unused",
            credential_id="unused", heartbeat_interval_seconds=60,
            next_tick_at=datetime(2026, 9, 6, tzinfo=UTC),
        ) is None
        assert slots.claim_temporary_resident_slot_assignment(
            db, agent_ids=[], user_id="unused", character_id="unused",
            credential_id="unused", heartbeat_interval_seconds=60,
            lease_seconds=60,
        ) is None
        assert statements == []
        assert not db.in_transaction()
    engine.dispose()
