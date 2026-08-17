from __future__ import annotations

from app.domains.device_home.application.list_local_world_apps import (
    LocalOwnerRequiredError,
)
from app.domains.device_home.domain.world_surface_policy import WorldSurfaceItem
from app.domains.device_home.ports.world_surface_repository import (
    WorldSurfaceRepository,
)


class WorldAppUnavailableError(LookupError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class GetLocalWorldApp:
    def __init__(self, repository: WorldSurfaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        current_user_id: str,
        world_id: str,
    ) -> WorldSurfaceItem:
        if not self._repository.is_local_owner(current_user_id):
            raise LocalOwnerRequiredError(current_user_id)
        world = self._repository.get_world(
            owner_user_id=current_user_id,
            world_id=world_id,
        )
        if world is None:
            raise WorldAppUnavailableError("world_membership_unavailable")
        if not world.launchable:
            raise WorldAppUnavailableError(
                world.launch_block_reason or "world_not_launchable"
            )
        return world
