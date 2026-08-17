from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core import browser_session
from app.core.db import get_db
from app.domains.device_home.api.device_home_schemas import (
    LocalWorldSurfaceRead,
    world_surface_read,
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
