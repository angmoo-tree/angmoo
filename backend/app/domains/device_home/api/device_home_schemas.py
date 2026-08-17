from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.device_home.domain.world_surface_policy import (
    WorldLaunchBlockReason,
    WorldMembershipRole,
    WorldSurface,
    WorldSurfacePage,
)


class DeviceHomeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorldSurfaceItemRead(DeviceHomeSchema):
    world_id: str
    name: str
    tagline: str
    banner_media_id: str | None = None
    banner_alt_text: str
    status: Literal["draft", "published", "archived"]
    visibility: Literal["private", "unlisted", "public"]
    readiness_status: Literal["not_ready", "publish_ready", "stale"]
    membership_role: WorldMembershipRole
    updated_at: datetime
    launchable: bool
    launch_block_reason: WorldLaunchBlockReason | None = None


class LocalWorldSurfaceRead(DeviceHomeSchema):
    schema_version: Literal["local-world-surface-v1"] = "local-world-surface-v1"
    surface: WorldSurface
    items: list[WorldSurfaceItemRead] = Field(default_factory=list)
    next_cursor: str | None = None


def world_surface_read(page: WorldSurfacePage) -> LocalWorldSurfaceRead:
    return LocalWorldSurfaceRead(
        surface=page.surface,
        items=[WorldSurfaceItemRead.model_validate(item.__dict__) for item in page.items],
        next_cursor=page.next_cursor,
    )
