"""Stable public surface for WorldCharacter execution policy."""

from app.domains.world_characters.infrastructure.sqlalchemy_owner_controlled_identity import (
    SqlAlchemyOwnerControlledIdentityRepository,
)
from app.domains.world_characters.infrastructure.autonomous_setup_contracts import (
    character_contract_hash,
)
from app.domains.world_characters.infrastructure.sqlalchemy_models import WorldCharacter
from app.domains.world_characters.infrastructure.sqlalchemy_setup_models import (
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
    enter_world,
    generate_setup,
    get_setup,
    get_world_entry,
    preflight_setup,
    reject_setup,
    retry_setup,
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
    "OWNER_REGENERATION_LIMIT_24H",
    "PROFILE_REGENERATION_LIMIT_24H",
    "WorldCharacterSetupConflictError",
    "WorldCharacterSetupError",
    "WorldCharacterSetupForbiddenError",
    "WorldCharacterSetupNotFoundError",
    "WorldCharacterSetupValidationError",
    "WorldActivityCandidate",
    "WorldActivityRepertoire",
    "WorldCharacter",
    "WorldCommunityProfile",
    "approve_setup",
    "character_contract_hash",
    "enter_world",
    "generate_setup",
    "get_setup",
    "get_world_entry",
    "is_owner_controlled_character",
    "owner_controlled_character_ids",
    "preflight_setup",
    "reject_setup",
    "retry_setup",
]
