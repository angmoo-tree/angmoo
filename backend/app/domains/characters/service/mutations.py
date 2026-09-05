"""Owner-facing Character mutations, before runtime activity/detail composition.

These functions retain the existing profile commit boundaries. They return the
same session-attached Character; callers continue existing activity/log steps.
"""
from uuid import uuid4
from sqlalchemy.orm import Session
from app.domains.characters import models, schemas
from app.domains.characters.contracts import CharacterOwner
from app.domains.characters.exceptions import AgentHandleConflictError, AgentHandleInvalidError, AgentProfileNameInvalidError
from app.domains.characters.service import profile
from app.domains.characters.service.access import _get_owned_character
from app.domains.characters.service.persona import ensure_persona_prompt_safety
from app.domains.characters.service.promotion import _set_promotion_usage
from app.domains.identity.service import demo_access as demo_lock
from app.policies import name_policy


def create_owned_character(db: Session, user: CharacterOwner, data: schemas.AgentCreate) -> models.Character:
    ensure_persona_prompt_safety(data)
    try:
        character = profile.create_character(
            db, user=user, character_id=f"char-{uuid4().hex[:12]}", data=data
        )
    except profile.CharacterHandleConflictError as exc:
        raise AgentHandleConflictError(str(exc)) from exc
    except profile.InvalidCharacterHandleError as exc:
        raise AgentHandleInvalidError(str(exc)) from exc
    _set_promotion_usage(character, data.promotion_usage_allowed)
    db.commit()
    db.refresh(character)
    return character


def update_owned_profile(db: Session, user: CharacterOwner, character_id: str, data: schemas.AgentProfileUpdate) -> tuple[models.Character, bool]:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    if data.name is not None and name_policy.is_blocked_name(data.name):
        raise AgentProfileNameInvalidError("사용할 수 없는 닉네임입니다.")
    if data.handle is not None and name_policy.is_blocked_name(data.handle):
        raise AgentHandleInvalidError("사용할 수 없는 핸들입니다.")
    old_avatar_url = character.avatar_url
    old_banner_url = character.banner_url
    try:
        profile.update_character_profile(db, character, data)
    except profile.CharacterHandleConflictError as exc:
        raise AgentHandleConflictError(str(exc)) from exc
    except profile.InvalidCharacterHandleError as exc:
        raise AgentHandleInvalidError(str(exc)) from exc
    changed = character.avatar_url != old_avatar_url or character.banner_url != old_banner_url
    return character, changed


def update_owned_promotion(db: Session, user: CharacterOwner, character_id: str, data: schemas.AgentPromotionUsageUpdate) -> models.Character:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    _set_promotion_usage(character, data.promotion_usage_allowed)
    db.commit()
    db.refresh(character)
    return character


def update_owned_persona(db: Session, user: CharacterOwner, character_id: str, data: schemas.AgentPersonaUpdate) -> models.Character:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    ensure_persona_prompt_safety(data)
    profile.update_character_persona(db, character, data)
    return character
