"""Current and target WorldCharacter checks at the caller's original read point."""

from collections.abc import Callable
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.world_characters import models
from app.domains.world_characters.exceptions import WorldCharacterSocialScopeError


def active_world_character(
    db: Session,
    *,
    character_id: str,
    error_type: Callable[[str], Exception] = WorldCharacterSocialScopeError,
) -> models.WorldCharacter:
    active = db.get(models.CharacterActiveWorld, character_id)
    if active is None:
        raise error_type("active_world_required")
    world_character = db.get(models.WorldCharacter, active.world_character_id)
    if (
        world_character is None
        or world_character.character_id != character_id
        or world_character.status != "active"
    ):
        raise error_type("active_world_character_invalid")
    return world_character


def world_character_for_character(
    db: Session,
    *,
    error_type: Callable[[str], Exception] = WorldCharacterSocialScopeError,
    world_id: str,
    character_id: str,
) -> models.WorldCharacter:
    world_character = db.scalar(
        select(models.WorldCharacter).where(
            models.WorldCharacter.world_id == world_id,
            models.WorldCharacter.character_id == character_id,
            models.WorldCharacter.status == "active",
        )
    )
    if world_character is None:
        raise error_type("target_world_character_invalid")
    return world_character


def get_world_character(
    db: Session, world_character_id: str
) -> models.WorldCharacter | None:
    return db.get(models.WorldCharacter, world_character_id)
