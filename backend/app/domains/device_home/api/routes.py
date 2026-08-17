from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core import browser_session
from app.core.db import get_db
from app.domains.device_home.api.device_home_schemas import (
    LocalWorldAppRead,
    LocalWorldSurfaceRead,
    world_app_read,
    world_surface_read,
)
from app.domains.device_home.application.get_local_world_app import (
    GetLocalWorldApp,
    WorldAppUnavailableError,
)
from app.domains.device_home.application.list_local_world_apps import (
    ListLocalWorldApps,
    LocalOwnerRequiredError,
)
from app.domains.device_home.domain.world_surface_policy import WorldSurface
from app.domains.device_home.infrastructure.sqlalchemy_world_surface_repository import (
    InvalidWorldSurfaceCursorError,
    SqlAlchemyWorldSurfaceRepository,
)


router = APIRouter(prefix="/worlds", tags=["device-home"])
logger = logging.getLogger(__name__)


@router.get("/mine", response_model=LocalWorldSurfaceRead)
def list_local_world_apps(
    request: Request,
    surface: WorldSurface,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> LocalWorldSurfaceRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        page = ListLocalWorldApps(SqlAlchemyWorldSurfaceRepository(db)).execute(
            current_user_id=current_user.id,
            surface=surface,
            limit=limit,
            cursor=cursor,
        )
    except LocalOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.reason_code,
        ) from exc
    except InvalidWorldSurfaceCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.reason_code,
        ) from exc
    return world_surface_read(page)


@router.get("/mine/{world_id}", response_model=LocalWorldAppRead)
def get_local_world_app(
    world_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> LocalWorldAppRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        world = GetLocalWorldApp(SqlAlchemyWorldSurfaceRepository(db)).execute(
            current_user_id=current_user.id,
            world_id=world_id,
        )
    except LocalOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.reason_code,
        ) from exc
    except WorldAppUnavailableError as exc:
        logger.info(
            "world_app_scope_denied reason=%s world_id=%s",
            exc.reason_code,
            world_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="world_app_unavailable",
        ) from exc
    return world_app_read(world)
