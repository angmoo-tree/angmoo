from __future__ import annotations

from app.domains.world_characters.exceptions import (
    OwnerControlledIdentityError,
    LocalOwnerRequiredError,
    OwnerWorldRequiredError,
    OwnerControlledIdentityNotFoundError,
    OwnerControlledIdentityConflictError,
    OwnerControlledRoleInvalidError,
)
from dataclasses import dataclass


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
