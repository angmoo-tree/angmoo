"""Social tool state admission, observation logging and Character error mapping."""

import logging
from sqlalchemy.orm import Session
from app.domains.characters import schemas
from app.domains.characters.service.state_notes import (
    _is_duplicate_memory_note,
    _state_observation_note,
)
from app.domains.social.contracts.agent_tools import AgentToolStateWorkflows
from app.domains.social.service.agent_tool_authorization import (
    _get_agent_tool_run,
    _raise_agent_tool_authorization_error,
)

logger = logging.getLogger("app.services.community")


class AgentToolStateService:
    def __init__(self, workflows: AgentToolStateWorkflows) -> None:
        self.workflows = workflows

    def save_agent_tool_character_state(
        self,
        db: Session,
        session_key: str,
        character_id: str,
        data: schemas.CharacterStateWrite,
    ) -> schemas.CharacterStateRead:
        run = _get_agent_tool_run(
            db,
            references=self.workflows,
            session_key=session_key,
            action="state",
            requested_character_id=character_id,
        )
        if run.character_id != character_id:
            _raise_agent_tool_authorization_error(
                action="state",
                reason="character_mismatch",
                session_key=session_key,
                run=run,
                requested_character_id=character_id,
            )
        existing_state = self.workflows.get_character_state(db, character_id)
        observation_note = _state_observation_note(data)
        if observation_note:
            self.workflows.log_activity(
                db,
                user_id=run.user_id,
                character_id=run.character_id,
                action_type="observation_note_saved",
                target_post_id=run.post_id,
                reason="agent_tool_state_observation_note",
                result=observation_note[:1000],
            )
        if _is_duplicate_memory_note(existing_state, data):
            self.workflows.log_activity(
                db,
                user_id=run.user_id,
                character_id=run.character_id,
                action_type="state_save_suppressed",
                target_post_id=run.post_id,
                reason="agent_tool_state_duplicate_memory_note",
                result="Suppressed duplicate memory_note state save.",
            )
            logger.info(
                "duplicate_state_save_suppressed character_id=%s run_id=%s session_key=%s",
                character_id,
                run.id,
                session_key,
            )
            return schemas.CharacterStateRead.model_validate(existing_state)
        state = self.workflows.save_character_state(db, character_id, data)
        self.workflows.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="state_saved",
            target_post_id=run.post_id,
            reason="agent_tool_state",
            result=(
                f"Saved state mood={state.mood}; "
                f"summary={state.summary[:300]}; memory_note={state.memory_note[:700]}"
            ),
        )
        return state
