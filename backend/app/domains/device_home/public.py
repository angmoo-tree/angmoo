"""Stable composition imports for the local Device Home domain."""

from sqlalchemy.orm import Session

from app.domains.device_home.api.routes import router
from app.domains.device_home.domain.world_surface_policy import WorldSurfaceItem
from app.domains.device_home.infrastructure.sqlalchemy_world_surface_repository import (
    SqlAlchemyWorldSurfaceRepository,
)


def get_device_home_world(
    db: Session, *, owner_user_id: str, world_id: str
) -> WorldSurfaceItem | None:
    return SqlAlchemyWorldSurfaceRepository(db).get_world(
        owner_user_id=owner_user_id,
        world_id=world_id,
    )


__all__ = ["WorldSurfaceItem", "get_device_home_world", "router"]
