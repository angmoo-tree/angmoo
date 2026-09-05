"""Owner, deletion, suspension and execution-mode admission for Characters."""
from sqlalchemy.orm import Session
from app.domains.characters import models
from app.domains.characters.contracts import CharacterOwner
from app.domains.characters.service import profile as community_crud
from app.domains.characters.exceptions import AgentNotFoundError, AgentSuspendedError, AgentExecutionModeError


LOCAL_MODE_LLM_BLOCKED_MESSAGE = (
    "로컬 모드 앵무는 서버 LLM 자율활동을 사용할 수 없습니다."
)

def _get_owned_character(
    db: Session, user: CharacterOwner, character_id: str
) -> models.Character:
    character = community_crud.get_character(db, character_id)
    if character is None or character.deleted_at is not None or character.owner_id != user.id:
        raise AgentNotFoundError(character_id)
    return character

def _ensure_not_suspended(character: models.Character) -> None:
    if character.moderation_status == "suspended":
        raise AgentSuspendedError("character_suspended")

def _is_local_mode(character: models.Character) -> bool:
    return character.execution_mode == "local"

def _ensure_llm_mode(character: models.Character) -> None:
    if _is_local_mode(character):
        raise AgentExecutionModeError(LOCAL_MODE_LLM_BLOCKED_MESSAGE)

def _ensure_local_mode(character: models.Character) -> None:
    if character.execution_mode != "local":
        raise AgentExecutionModeError("로컬 모드 앵무에서만 local key를 사용할 수 있습니다.")
