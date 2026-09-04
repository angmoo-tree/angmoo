"""Home/Studio queries and the trusted World Package read projection.

The caller owns the Session and transaction. Public HTTP queries enforce the
claimed installation owner; the internal projection preserves membership scope
without turning draft/unlaunchable results into HTTP errors.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.device_home.contracts import WorldSurface, WorldSurfaceItem, WorldSurfacePage
from app.domains.device_home.exceptions import LocalOwnerRequiredError, WorldAppUnavailableError
from app.domains.device_home.repository import SqlAlchemyWorldSurfaceRepository


def list_local_world_apps(
    db: Session,
    *,
    current_user_id: str,
    surface: WorldSurface,
    limit: int,
    cursor: str | None,
) -> WorldSurfacePage:
    repository = SqlAlchemyWorldSurfaceRepository(db)
    if not repository.is_local_owner(current_user_id):
        raise LocalOwnerRequiredError(current_user_id)
    return repository.list_worlds(
        owner_user_id=current_user_id, surface=surface, limit=limit, cursor=cursor,
    )


def get_local_world_app(
    db: Session, *, current_user_id: str, world_id: str,
) -> WorldSurfaceItem:
    repository = SqlAlchemyWorldSurfaceRepository(db)
    if not repository.is_local_owner(current_user_id):
        raise LocalOwnerRequiredError(current_user_id)
    world = repository.get_world(owner_user_id=current_user_id, world_id=world_id)
    if world is None:
        raise WorldAppUnavailableError("world_membership_unavailable")
    if not world.launchable:
        raise WorldAppUnavailableError(world.launch_block_reason or "world_not_launchable")
    return world


def get_device_home_world(
    db: Session, *, owner_user_id: str, world_id: str,
) -> WorldSurfaceItem | None:
    """Read an existing membership projection inside a trusted caller transaction."""
    return SqlAlchemyWorldSurfaceRepository(db).get_world(
        owner_user_id=owner_user_id, world_id=world_id,
    )
