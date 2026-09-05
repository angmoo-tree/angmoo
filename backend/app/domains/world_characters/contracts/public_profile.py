"""World-scoped public profile values for Local product surfaces."""

from __future__ import annotations

from app.domains.world_characters.exceptions import (
    WorldCharacterProfileError,
    WorldCharacterProfileNotFoundError,
    WorldCharacterProfileForbiddenError,
)
from dataclasses import dataclass
from typing import Literal


WorldCharacterControlMode = Literal["autonomous", "owner_controlled"]


@dataclass(frozen=True, slots=True)
class WorldCharacterPublicProfile:
    world_id: str
    world_character_id: str
    character_id: str
    display_name: str
    handle: str | None
    avatar_url: str | None
    banner_url: str | None
    intro: str
    role_key: str | None
    control_mode: WorldCharacterControlMode
    status: Literal["active"] = "active"
    profile_capability: Literal["available"] = "available"


__all__ = [
    "WorldCharacterControlMode",
    "WorldCharacterProfileError",
    "WorldCharacterProfileForbiddenError",
    "WorldCharacterProfileNotFoundError",
    "WorldCharacterPublicProfile",
]
