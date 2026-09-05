"""WorldCharacter authorization required by Social writes, in the caller Session."""
from typing import Protocol
from sqlalchemy.orm import Session
from app.domains.world_characters import models
from app.domains.world_characters.exceptions import WorldCharacterSocialScopeError
from app.domains.worlds.service.character_entry import get_character_entry_membership


class SocialScopeCharacter(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def owner_id(self) -> str: ...


def validate_social_author_scope(db: Session, *, world_id: str, author_world_character_id: str, character: SocialScopeCharacter) -> None:
    world_character = db.get(models.WorldCharacter, author_world_character_id)
    if (
        world_character is None
        or world_character.world_id != world_id
        or world_character.character_id != character.id
        or world_character.status != "active"
    ):
        raise WorldCharacterSocialScopeError("world_scope_invalid")


def resolve_social_target_scope(db: Session, *, target_world_id: str, character: SocialScopeCharacter) -> str:
    active_world = db.get(models.CharacterActiveWorld, character.id)
    if active_world is None:
        raise WorldCharacterSocialScopeError("active_world_required")
    world_character = db.get(models.WorldCharacter, active_world.world_character_id)
    if (
        world_character is None
        or world_character.character_id != character.id
        or world_character.world_id != target_world_id
        or world_character.status != "active"
    ):
        raise WorldCharacterSocialScopeError("target_world_not_active")
    membership = get_character_entry_membership(db, world_character.membership_id)
    if (
        membership is None
        or membership.world_id != target_world_id
        or membership.user_id != character.owner_id
        or membership.status != "active"
    ):
        raise WorldCharacterSocialScopeError("world_membership_not_active")
    return world_character.id
