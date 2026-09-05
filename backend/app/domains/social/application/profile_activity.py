"""Use case for current-World WorldCharacter social profile activity."""

from __future__ import annotations

from app.domains.social.contracts.profile_activity import (
    WorldCharacterSocialProfilePage,
    WorldCharacterSocialProfileQuery,
    WorldCharacterSocialProfileValidationError,
)
from app.domains.social.ports.profile_activity import (
    WorldCharacterSocialProfileReader,
)


def read_world_character_social_profile(
    reader: WorldCharacterSocialProfileReader,
    query: WorldCharacterSocialProfileQuery,
) -> WorldCharacterSocialProfilePage:
    if not query.world_id.strip() or not query.world_character_id.strip():
        raise WorldCharacterSocialProfileValidationError()
    if not query.current_user_id.strip():
        raise WorldCharacterSocialProfileValidationError()
    if query.tab not in {"posts", "replies", "likes"}:
        raise WorldCharacterSocialProfileValidationError()
    if query.limit < 1 or query.limit > 20:
        raise WorldCharacterSocialProfileValidationError()
    return reader.read(query)


__all__ = ["read_world_character_social_profile"]
