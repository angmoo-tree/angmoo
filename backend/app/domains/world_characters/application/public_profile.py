"""Use cases for same-World WorldCharacter public profiles."""

from __future__ import annotations

from app.domains.world_characters.domain.public_profile import (
    WorldCharacterPublicProfile,
)
from app.domains.world_characters.ports.public_profile import (
    WorldCharacterPublicProfileReader,
)


def list_world_character_profiles(
    reader: WorldCharacterPublicProfileReader,
    *,
    world_id: str,
    current_user_id: str,
) -> tuple[WorldCharacterPublicProfile, ...]:
    return reader.list_for_world(
        world_id=world_id,
        current_user_id=current_user_id,
    )


def get_world_character_profile(
    reader: WorldCharacterPublicProfileReader,
    *,
    world_id: str,
    world_character_id: str,
    current_user_id: str,
) -> WorldCharacterPublicProfile:
    return reader.get_for_world(
        world_id=world_id,
        world_character_id=world_character_id,
        current_user_id=current_user_id,
    )


__all__ = [
    "get_world_character_profile",
    "list_world_character_profiles",
]
