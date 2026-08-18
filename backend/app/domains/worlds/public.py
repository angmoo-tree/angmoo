"""Single supported entrypoint for World Creator use cases.

API routes and other domains import this module instead of reaching into the
SQLAlchemy adapter. Compatibility modules may re-export these names while the
remaining L3 boundaries migrate in later pull requests.
"""

from app.domains.worlds.infrastructure.sqlalchemy_world_creator import (
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

__all__ = [
    "WorldArchivedError",
    "WorldBannerValidationError",
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
    "validate_world_definition",
]
