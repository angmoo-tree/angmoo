from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class OwnerControlledProfile:
    display_name: str
    avatar_url: str
    intro: str
    role_key: str | None
    preferred_address: str
    interests: tuple[str, ...]
    background: str


@dataclass(frozen=True)
class OwnerControlledIdentitySnapshot:
    world_character_id: str
    world_id: str
    character_id: str
    control_mode: str
    status: str
    autonomous_enabled: bool
    version: int
    profile: OwnerControlledProfile


__all__ = [
    "LocalOwnerRequiredError",
    "OwnerControlledIdentityConflictError",
    "OwnerControlledIdentityError",
    "OwnerControlledIdentityNotFoundError",
    "OwnerControlledIdentitySnapshot",
    "OwnerControlledProfile",
    "OwnerControlledRoleInvalidError",
    "OwnerWorldRequiredError",
]
