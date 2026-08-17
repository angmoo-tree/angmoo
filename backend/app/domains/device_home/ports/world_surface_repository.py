from __future__ import annotations

from typing import Protocol

from app.domains.device_home.domain.world_surface_policy import (
    WorldSurface,
    WorldSurfacePage,
)


class WorldSurfaceRepository(Protocol):
    def is_local_owner(self, user_id: str) -> bool: ...

    def list_worlds(
        self,
        *,
        owner_user_id: str,
        surface: WorldSurface,
        limit: int,
        cursor: str | None,
    ) -> WorldSurfacePage: ...
