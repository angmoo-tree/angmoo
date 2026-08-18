"""Compatibility facade for world services not yet migrated by L3.

World Creator behavior is owned by ``app.domains.worlds.public``. The character
ownership helper remains here until the World Character boundary moves in PR C.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import models
from app.domains.worlds.public import (
    WorldArchivedError,
    WorldBannerValidationError,
    WorldCreatorRoleRequiredError,
    WorldDefinitionIncompleteError,
    WorldDefinitionValidationError,
    WorldMembershipRequiredError,
    WorldNotFoundError,
    WorldOwnerRoleRequiredError,
    WorldRowVersionConflictError,
    WorldServiceError,
    archive_world,
    create_world,
    get_active_membership,
    get_creator_context,
    get_generation_context,
    get_world,
    get_world_read,
    publish_world,
    remove_world_banner,
    require_creator_access,
    require_owner_access,
    require_world_read_access,
    update_world,
    upload_world_banner,
    validate_world_definition,
)


class WorldCharacterOwnershipError(WorldServiceError):
    reason_code = "world_character_owner_mismatch"


def validate_world_character_membership(
    db: Session,
    *,
    world_id: str,
    character_id: str,
    membership_id: str,
) -> tuple[models.Character, models.WorldMembership]:
    character = db.get(models.Character, character_id)
    membership = db.get(models.WorldMembership, membership_id)
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


__all__ = [
    "WorldArchivedError",
    "WorldBannerValidationError",
    "WorldCharacterOwnershipError",
    "WorldCreatorRoleRequiredError",
    "WorldDefinitionIncompleteError",
    "WorldDefinitionValidationError",
    "WorldMembershipRequiredError",
    "WorldNotFoundError",
    "WorldOwnerRoleRequiredError",
    "WorldRowVersionConflictError",
    "WorldServiceError",
    "archive_world",
    "create_world",
    "get_active_membership",
    "get_creator_context",
    "get_generation_context",
    "get_world",
    "get_world_read",
    "publish_world",
    "remove_world_banner",
    "require_creator_access",
    "require_owner_access",
    "require_world_read_access",
    "update_world",
    "upload_world_banner",
    "validate_world_character_membership",
    "validate_world_definition",
]
