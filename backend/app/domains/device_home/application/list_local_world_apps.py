from __future__ import annotations

from app.domains.device_home.domain.world_surface_policy import (
    WorldSurface,
    WorldSurfacePage,
)
from app.domains.device_home.ports.world_surface_repository import (
    WorldSurfaceRepository,
)


class LocalOwnerRequiredError(PermissionError):
    reason_code = "local_owner_required"


class ListLocalWorldApps:
    def __init__(self, repository: WorldSurfaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        current_user_id: str,
        surface: WorldSurface,
        limit: int,
        cursor: str | None,
    ) -> WorldSurfacePage:
        if not self._repository.is_local_owner(current_user_id):
            raise LocalOwnerRequiredError(current_user_id)
        return self._repository.list_worlds(
            owner_user_id=current_user_id,
            surface=surface,
            limit=limit,
            cursor=cursor,
        )
