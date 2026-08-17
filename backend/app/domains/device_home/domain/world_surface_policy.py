from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


WorldSurface = Literal["device_home", "creator_studio"]
WorldMembershipRole = Literal["owner", "editor", "member"]
WorldLaunchBlockReason = Literal[
    "world_archived",
    "world_not_published",
    "world_not_ready",
    "world_private",
]


@dataclass(frozen=True)
class WorldSurfaceItem:
    world_id: str
    name: str
    tagline: str
    banner_media_id: str | None
    banner_alt_text: str
    status: str
    visibility: str
    readiness_status: str
    membership_role: WorldMembershipRole
    updated_at: datetime
    launchable: bool
    launch_block_reason: WorldLaunchBlockReason | None


@dataclass(frozen=True)
class WorldSurfacePage:
    surface: WorldSurface
    items: tuple[WorldSurfaceItem, ...]
    next_cursor: str | None = None


def launchability(
    *,
    status: str,
    visibility: str,
    readiness_status: str,
) -> tuple[bool, WorldLaunchBlockReason | None]:
    if status == "archived":
        return False, "world_archived"
    if status != "published":
        return False, "world_not_published"
    if readiness_status != "publish_ready":
        return False, "world_not_ready"
    if visibility not in {"public", "unlisted"}:
        return False, "world_private"
    return True, None
