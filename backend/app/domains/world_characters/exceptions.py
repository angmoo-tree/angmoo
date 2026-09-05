"""Stable WorldCharacter identity, profile, lifecycle and validation errors."""
from __future__ import annotations

from typing import Mapping


class OwnerControlledIdentityError(Exception):
    reason_code = "owner_controlled_identity_error"

class LocalOwnerRequiredError(OwnerControlledIdentityError):
    reason_code = "local_owner_required"

class OwnerWorldRequiredError(OwnerControlledIdentityError):
    reason_code = "owner_world_required"

class OwnerControlledIdentityNotFoundError(OwnerControlledIdentityError):
    reason_code = "owner_controlled_identity_not_found"

class OwnerControlledIdentityConflictError(OwnerControlledIdentityError):
    reason_code = "owner_controlled_identity_exists"

class OwnerControlledRoleInvalidError(OwnerControlledIdentityError):
    reason_code = "owner_controlled_role_invalid"

class WorldCharacterProfileError(Exception):
    reason_code = "world_character_profile_error"

class WorldCharacterProfileNotFoundError(WorldCharacterProfileError):
    reason_code = "target_profile_unavailable"

class WorldCharacterProfileForbiddenError(WorldCharacterProfileError):
    reason_code = "world_character_profile_forbidden"

class StudioWorldCharacterLifecycleError(Exception):
    reason_code = "studio_world_character_lifecycle_error"

    def __init__(self, reason_code: str | None = None) -> None:
        if reason_code is not None:
            self.reason_code = reason_code
        super().__init__(self.reason_code)

class StudioWorldCharacterNotFoundError(StudioWorldCharacterLifecycleError):
    reason_code = "world_character_not_found"

class StudioWorldCharacterForbiddenError(StudioWorldCharacterLifecycleError):
    reason_code = "character_not_owned"

class StudioWorldCharacterConflictError(StudioWorldCharacterLifecycleError):
    reason_code = "stale_world_character_version"

class StudioWorldCharacterValidationError(StudioWorldCharacterLifecycleError):
    reason_code = "world_character_ineligible"

class StudioWorldCharacterBusyError(StudioWorldCharacterConflictError):
    reason_code = "world_character_run_in_progress"

class WorldCharacterContractError(ValueError):
    def __init__(
        self,
        reason_code: str,
        *,
        details: Mapping[str, int | str] | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.details = dict(details or {})
        super().__init__(reason_code)


class WorldCharacterSetupError(Exception):
    reason_code = "world_character_setup_error"


class WorldCharacterSetupNotFoundError(WorldCharacterSetupError):
    reason_code = "world_character_not_found"


class WorldCharacterSetupForbiddenError(WorldCharacterSetupError):
    reason_code = "character_not_owned"


class WorldCharacterSetupConflictError(WorldCharacterSetupError):
    reason_code = "setup_in_progress"

    def __init__(self, reason_code: str | None = None) -> None:
        if reason_code is not None:
            self.reason_code = reason_code
        super().__init__(self.reason_code)


class WorldCharacterSetupValidationError(WorldCharacterSetupError):
    reason_code = "world_character_ineligible"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


from app.domains.worlds.contracts import WorldServiceError


class WorldCharacterOwnershipError(WorldServiceError):
    reason_code = "world_character_owner_mismatch"


class WorldCharacterSocialScopeError(Exception):
    """The active WorldCharacter cannot author in the requested canonical scope."""
