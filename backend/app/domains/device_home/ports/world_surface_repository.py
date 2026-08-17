from __future__ import annotations

from typing import Protocol

from app.domains.device_home.domain.world_surface_policy import (
    WorldSurface,
    WorldSurfaceItem,
    WorldSurfacePage,
)


class WorldSurfaceRepository(Protocol):
    def is_local_owner(self, user_id: str) -> bool: ...

    def get_world(
        self,
        *,
        owner_user_id: str,
        world_id: str,
    ) -> WorldSurfaceItem | None: ...

    def list_worlds(
        self,
        *,
        owner_user_id: str,
        surface: WorldSurface,
        limit: int,
        cursor: str | None,
    ) -> WorldSurfacePage: ...
