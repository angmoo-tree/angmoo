from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app import models
from app.core.unit_of_work import deferred_commits
from app.domains.characters.schemas import AgentCharacterStateWrite, CharacterStateWrite
from app.domains.characters.service import state as character_state
from app.runtime.social.agent_tool_state import agent_tool_state
from test_social_event_runtime import _engine, _seed


def test_tool_state_duplicate_note_preserves_state_and_log_order_with_caller_rollback():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = models.AgentRun(
            id="tool-state-contract",
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
            agent_id="resident-contract",
            session_key="tool-state-contract-session",
            status="running",
        )
        db.add(run)
        db.commit()
        character_state.save_character_state(
            db,
            fixture.actor.id,
            CharacterStateWrite(
                mood="calm", summary="Original state", memory_note="A Shared Memory"
            ),
        )
        original = character_state.get_character_state(db, fixture.actor.id)
        original_updated = original.updated_at
        commits = []
        event.listen(db, "before_commit", lambda *args: commits.append("commit"))
        insert_actions = []
        event.listen(
            db,
            "before_flush",
            lambda session, *_: insert_actions.extend(
                row.action_type
                for row in session.new
                if isinstance(row, models.AgentActivityLog)
            ),
        )
        with deferred_commits():
            result = agent_tool_state.save_agent_tool_character_state(
                db,
                run.session_key,
                fixture.actor.id,
                AgentCharacterStateWrite(
                    mood="excited",
                    summary="Should remain original",
                    memory_note="  a\tSHARED   memory  ",
                    observation_note="  observed a new reply  ",
                ),
            )
            assert character_state.get_character_state(db, fixture.actor.id) is original
            assert result.mood == "calm"
            assert result.summary == "Original state"
            assert result.memory_note == "A Shared Memory"
            assert original.updated_at == original_updated
            assert insert_actions == ["observation_note_saved", "state_save_suppressed"]
            logs = list(db.scalars(select(models.AgentActivityLog)))
            assert len(logs) == 2
            assert {row.reason for row in logs} == {
                "agent_tool_state_observation_note",
                "agent_tool_state_duplicate_memory_note",
            }
            assert (
                next(
                    row.result
                    for row in logs
                    if row.action_type == "observation_note_saved"
                )
                == "observed a new reply"
            )
            assert commits == []
            del logs
        db.rollback()
        assert list(db.scalars(select(models.AgentActivityLog))) == []
        assert character_state.get_character_state(db, fixture.actor.id) is original
        assert original.memory_note == "A Shared Memory"
        with deferred_commits():
            updated = agent_tool_state.save_agent_tool_character_state(
                db,
                run.session_key,
                fixture.actor.id,
                CharacterStateWrite(
                    mood="curious",
                    summary="A later state",
                    memory_note="A different memory",
                ),
            )
            assert updated.memory_note == "A different memory"
            assert character_state.get_character_state(db, fixture.actor.id) is original
            assert original.summary == "A later state"
            saved_log = db.scalar(select(models.AgentActivityLog))
            assert saved_log.action_type == "state_saved"
            assert saved_log.reason == "agent_tool_state"
            assert commits == []
        db.rollback()
        assert original.summary == "Original state"
        assert original.memory_note == "A Shared Memory"
        assert list(db.scalars(select(models.AgentActivityLog))) == []
        assert commits == []
    engine.dispose()
