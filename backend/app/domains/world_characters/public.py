"""Stable public surface for WorldCharacter execution policy."""

from app.domains.world_characters.infrastructure.sqlalchemy_owner_controlled_identity import (
    SqlAlchemyOwnerControlledIdentityRepository,
)


def is_owner_controlled_character(db, character_id: str) -> bool:
    return SqlAlchemyOwnerControlledIdentityRepository(
        db
    ).is_owner_controlled_character(character_id)


def owner_controlled_character_ids(
    db, character_ids: set[str]
) -> set[str]:
    return SqlAlchemyOwnerControlledIdentityRepository(
        db
    ).owner_controlled_character_ids(character_ids)

__all__ = [
    "is_owner_controlled_character",
    "owner_controlled_character_ids",
]
