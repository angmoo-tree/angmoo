"""Verify Character ownership and World membership in the same caller Session."""
from sqlalchemy.orm import Session
from app.domains.characters.service.profile import get_character
from app.domains.worlds.service.character_entry import get_character_entry_membership
from app.domains.world_characters.exceptions import WorldCharacterOwnershipError


def validate_world_character_membership(
    db: Session,
    *,
    world_id: str,
    character_id: str,
    membership_id: str,
):
    character = get_character(db, character_id)
    membership = get_character_entry_membership(db, membership_id)
    if character is None or character.deleted_at is not None:
        raise WorldCharacterOwnershipError(character_id)
    if (
        membership is None
        or membership.world_id != world_id
        or membership.user_id != character.owner_id
        or membership.status != "active"
    ):
        raise WorldCharacterOwnershipError(character_id)
    return character, membership
