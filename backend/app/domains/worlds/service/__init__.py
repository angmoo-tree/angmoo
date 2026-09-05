"""Supported World use cases and definition queries.

seed_world and ensure_no_specific_role join the supplied Session and only flush.
Creator mutation functions own commit/rollback as documented in creator.py; no
ORM model is exported as a substitute for a cross-domain service.
"""

from app.domains.worlds.service.creator import (
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
    WorldSeedOutcome,
    archive_world,
    create_world,
    get_active_membership,
    get_creator_context,
    get_generation_context,
    is_enabled_world_role,
    get_world,
    get_world_read,
    publish_world,
    remove_world_banner,
    reschedule_world_autonomy_slots,
    seed_world,
    require_creator_access,
    require_owner_access,
    require_world_read_access,
    update_world,
    upload_world_banner,
    validate_world_definition,
)
from app.domains.worlds.service.generation_context import (
    build_world_generation_context,
)
from app.domains.worlds.service.definition import (
    WORLD_CONTRACT_VERSION,
    refresh_world_contract,
    world_contract_hash,
)
from app.domains.worlds.service.reserved_roles import (
    ReservedWorldRoleConflictError,
    ensure_no_specific_role,
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
    "WorldSeedOutcome",
    "archive_world",
    "create_world",
    "get_active_membership",
    "get_creator_context",
    "get_generation_context",
    "is_enabled_world_role",
    "get_world",
    "get_world_read",
    "publish_world",
    "remove_world_banner",
    "reschedule_world_autonomy_slots",
    "seed_world",
    "require_creator_access",
    "require_owner_access",
    "require_world_read_access",
    "update_world",
    "upload_world_banner",
    "validate_world_definition",
    "build_world_generation_context",
    "WORLD_CONTRACT_VERSION",
    "refresh_world_contract",
    "world_contract_hash",
    "ReservedWorldRoleConflictError",
    "ensure_no_specific_role",
]
