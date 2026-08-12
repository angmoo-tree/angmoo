from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import get_current_user, get_db
from app.services import daily_activity_plans, social_memory_read


router = APIRouter(prefix="/characters", tags=["world-activity-runtime"])


def _raise_plan_error(exc: daily_activity_plans.DailyActivityPlanError) -> None:
    if isinstance(exc, daily_activity_plans.DailyActivityPlanNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, daily_activity_plans.DailyActivityPlanForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, daily_activity_plans.DailyActivityPlanConflictError):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc

def _raise_social_memory_error(exc: social_memory_read.SocialMemoryReadError) -> None:
    if isinstance(exc, social_memory_read.SocialMemoryNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, social_memory_read.SocialMemoryForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc



@router.get(
    "/{character_id}/worlds/{world_id}/activity-plan",
    response_model=schemas.DailyActivityPlanRead,
)
def get_daily_activity_plan(
    character_id: str,
    world_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.DailyActivityPlanRead:
    try:
        return daily_activity_plans.get_activity_plan(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
        )
    except daily_activity_plans.DailyActivityPlanError as exc:
        _raise_plan_error(exc)


@router.post(
    "/{character_id}/worlds/{world_id}/activity-plan/prepare",
    response_model=schemas.DailyActivityPlanRead,
)
def prepare_daily_activity_plan(
    character_id: str,
    world_id: str,
    data: schemas.DailyActivityPlanPrepareCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.DailyActivityPlanRead:
    try:
        return daily_activity_plans.prepare_activity_plan(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
            data=data,
        )
    except daily_activity_plans.DailyActivityPlanError as exc:
        _raise_plan_error(exc)


@router.patch(
    "/{character_id}/worlds/{world_id}/activity-runtime-mode",
    response_model=schemas.WorldCharacterRuntimeModeRead,
)
def update_world_character_activity_runtime_mode(
    character_id: str,
    world_id: str,
    data: schemas.WorldCharacterRuntimeModeUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterRuntimeModeRead:
    try:
        return daily_activity_plans.update_activity_runtime_mode(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
            data=data,
        )
    except daily_activity_plans.DailyActivityPlanError as exc:
        _raise_plan_error(exc)


@router.get(
    "/{character_id}/worlds/{world_id}/social-memory",
    response_model=schemas.SocialMemoryDiagnosticsRead,
)
def get_world_character_social_memory(
    character_id: str,
    world_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.SocialMemoryDiagnosticsRead:
    """Return owner-only P6 evidence, directional relationships, and joint state."""

    try:
        return social_memory_read.get_owner_diagnostics(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
        )
    except social_memory_read.SocialMemoryReadError as exc:
        _raise_social_memory_error(exc)
