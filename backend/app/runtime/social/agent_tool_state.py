"""Connect Social tool state to the original caller-Session Character and activity writes."""

from sqlalchemy.orm import Session
from app.domains.characters.service import state as character_state
from app.domains.routines.service import activity_logs
from app.domains.social.contracts.agent_tools import ToolCharacterState
from app.domains.social.service.agent_tool_state import AgentToolStateService
from app.runtime.social.agent_tool_authorization import RuntimeAgentToolReferences

from app.domains.characters import schemas
from app.domains.characters.contracts import CharacterOwner
from app.domains.characters.exceptions import CharacterStateNotFoundError
from app.domains.social.exceptions import CharacterNotFoundError


def save_character_state(
    db: Session, character_id: str, data: schemas.CharacterStateWrite
) -> schemas.CharacterStateRead:
    try:
        return character_state.save_character_state(db, character_id, data)
    except CharacterStateNotFoundError as exc:
        raise CharacterNotFoundError(str(exc)) from exc


def save_character_state_for_user(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    data: schemas.CharacterStateWrite,
) -> schemas.CharacterStateRead:
    try:
        return character_state.save_character_state_for_user(
            db, user, character_id, data
        )
    except CharacterStateNotFoundError as exc:
        raise CharacterNotFoundError(str(exc)) from exc


class RuntimeAgentToolStateWorkflows(RuntimeAgentToolReferences):
    def save_character_state(
        self, db: Session, character_id: str, data: schemas.CharacterStateWrite
    ) -> schemas.CharacterStateRead:
        return save_character_state(db, character_id, data)

    def get_character_state(
        self, db: Session, character_id: str
    ) -> ToolCharacterState | None:
        return character_state.get_character_state(db, character_id)

    def log_activity(
        self,
        db: Session,
        *,
        user_id: str,
        character_id: str,
        action_type: str,
        target_post_id: str | None,
        reason: str,
        result: str,
    ) -> object:
        return activity_logs.log_activity(
            db,
            user_id=user_id,
            character_id=character_id,
            action_type=action_type,
            target_post_id=target_post_id,
            reason=reason,
            result=result,
        )


agent_tool_state = AgentToolStateService(RuntimeAgentToolStateWorkflows())
