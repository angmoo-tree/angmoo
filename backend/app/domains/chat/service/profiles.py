"""Chat profile reads and response conversion using Character-owned lookup."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.characters.service import profile as character_profile
from app.domains.chat import schemas
from app.domains.chat.contracts.context import (
    ChatCharacter,
    ChatUser,
)
from app.domains.chat.exceptions import (
    MessageForbiddenError,
    MessageNotFoundError,
)


def _get_character(db: Session, character_id: str) -> ChatCharacter:
    character = character_profile.get_character(db, character_id)
    if character is None or character.deleted_at is not None:
        raise MessageNotFoundError("앵무를 찾을 수 없습니다.")
    return character


def _get_owned_character(
    db: Session, user: ChatUser, character_id: str
) -> ChatCharacter:
    character = _get_character(db, character_id)
    if character.owner_id != user.id:
        raise MessageForbiddenError("이 앵무 설정을 바꿀 수 없습니다.")
    return character


def _owned_agent_refs(db: Session, user: ChatUser) -> list[schemas.ProfileRef]:
    characters = character_profile.list_message_source_characters(db, user.id)
    return [_character_ref(character) for character in characters]


def _user_ref(user: ChatUser) -> schemas.ProfileRef:
    return schemas.ProfileRef(
        profile_type="user", id=user.id, display_name=user.display_name
    )


def _character_ref(character: ChatCharacter) -> schemas.ProfileRef:
    return schemas.ProfileRef(
        profile_type="character",
        id=character.id,
        display_name=character.name,
        handle=character.handle,
        avatar_url=character.avatar_url,
        banner_url=character.banner_url,
    )


from app.domains.chat.contracts import CharacterResponseProfile

def _response_profile(character: ChatCharacter) -> CharacterResponseProfile:
    return CharacterResponseProfile(
        name=character.name,
        handle=character.handle,
        one_liner=character.one_liner,
        personality=character.personality,
        speech_style=character.speech_style,
        worldview=character.worldview,
        topic_preferences=character.topic_preferences,
        safety_rules=character.safety_rules,
    )
