"""Stable public surface for WorldCharacter execution policy."""

from app.domains.world_characters.service.owner_identity import (
    OwnerControlledIdentityService,
)
from app.domains.world_characters.contracts.public_profile import (
    WorldCharacterProfileError,
    WorldCharacterProfileForbiddenError,
    WorldCharacterProfileNotFoundError,
    WorldCharacterPublicProfile,
)
from app.domains.world_characters.contracts.owner_identity import (
    OwnerControlledIdentityError,
)
from app.domains.world_characters.contracts.seed import (
    AutonomousWorldCharacterSeedData,
)
from app.domains.world_characters.contracts.runtime_modes import (
    AUTONOMOUS_ACTIVITY_RUNTIME_MODE,
    AUTONOMOUS_FEED_RUNTIME_MODE,
    AUTONOMOUS_RUNTIME_MODE_PAIR,
    AutonomousRuntimeModePair,
    is_expected_autonomous_runtime_pair,
)
from app.domains.world_characters.service.setup_validation import (
    character_contract_hash,
)
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.models import (
    WorldActivityCandidate,
    WorldActivityRepertoire,
    WorldCommunityProfile,
)
from app.domains.world_characters.infrastructure.sqlalchemy_autonomous_setup import (
    OWNER_REGENERATION_LIMIT_24H,
    PROFILE_REGENERATION_LIMIT_24H,
    WorldCharacterSetupConflictError,
    WorldCharacterSetupError,
    WorldCharacterSetupForbiddenError,
    WorldCharacterSetupNotFoundError,
    WorldCharacterSetupValidationError,
    approve_setup,
    count_enabled_autonomous_world_characters,
    enter_world,
    generate_setup,
    get_setup,
    get_world_entry,
    preflight_setup,
    reject_setup,
    retry_setup,
    lock_world_autonomy_capacity,
    selected_autonomous_world_character,
    set_active_world_character_autonomy,
    update_world_character_role,
)
from app.domains.world_characters.contracts.studio_lifecycle import (
    StudioWorldCharacterBusyError,
    StudioWorldCharacterConflictError,
    StudioWorldCharacterForbiddenError,
    StudioWorldCharacterLifecycleError,
    StudioWorldCharacterNotFoundError,
    StudioWorldCharacterValidationError,
)
from app.domains.world_characters.service.seed import (
    seed_autonomous_world_character,
)
from app.domains.world_characters.infrastructure.sqlalchemy_runtime_modes import (
    AutonomousRuntimeModeRepairResult,
    reconcile_local_autonomous_runtime_modes,
)


from app.domains.world_characters.service.owner_identity import (
    is_owner_controlled_character, owner_controlled_character_ids,
)

__all__ = [
    "OWNER_REGENERATION_LIMIT_24H",
    "AutonomousWorldCharacterSeedData",
    "AUTONOMOUS_ACTIVITY_RUNTIME_MODE",
    "AUTONOMOUS_FEED_RUNTIME_MODE",
    "AUTONOMOUS_RUNTIME_MODE_PAIR",
    "AutonomousRuntimeModePair",
    "AutonomousRuntimeModeRepairResult",
    "OwnerControlledIdentityError",
    "PROFILE_REGENERATION_LIMIT_24H",
    "WorldCharacterSetupConflictError",
    "WorldCharacterSetupError",
    "WorldCharacterSetupForbiddenError",
    "WorldCharacterSetupNotFoundError",
    "WorldCharacterSetupValidationError",
    "StudioWorldCharacterBusyError",
    "StudioWorldCharacterConflictError",
    "StudioWorldCharacterForbiddenError",
    "StudioWorldCharacterLifecycleError",
    "StudioWorldCharacterNotFoundError",
    "StudioWorldCharacterValidationError",
    "WorldActivityCandidate",
    "WorldActivityRepertoire",
    "WorldCharacter",
    "WorldCommunityProfile",
    "WorldCharacterProfileError",
    "WorldCharacterProfileForbiddenError",
    "WorldCharacterProfileNotFoundError",
    "WorldCharacterPublicProfile",
    "OwnerControlledIdentityService",
    "approve_setup",
    "character_contract_hash",
    "count_enabled_autonomous_world_characters",
    "enter_world",
    "generate_setup",
    "get_setup",
    "get_world_entry",
    "is_owner_controlled_character",
    "is_expected_autonomous_runtime_pair",
    "lock_world_autonomy_capacity",
    "owner_controlled_character_ids",
    "preflight_setup",
    "reconcile_local_autonomous_runtime_modes",
    "reject_setup",
    "retry_setup",
    "selected_autonomous_world_character",
    "set_active_world_character_autonomy",
    "update_world_character_role",
    "seed_autonomous_world_character",
]
