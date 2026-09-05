"""Owner daily plan and runtime-mode HTTP endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api.identity_dependencies import get_current_user
from app.domains.routines import exceptions, schemas
from app.domains.routines.contracts.plans import PlanOwner, PlanReferences
from app.domains.routines.dependencies import get_plan_references
from app.domains.routines.service import plans as routines


router = APIRouter()


def _raise_plan_error(exc: exceptions.DailyActivityPlanError) -> None:
    if isinstance(exc, exceptions.DailyActivityPlanNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, exceptions.DailyActivityPlanForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, exceptions.DailyActivityPlanConflictError):
        status_code = status.HTTP_409_CONFLICT
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
    user: PlanOwner = Depends(get_current_user),
    references: PlanReferences = Depends(get_plan_references),
) -> schemas.DailyActivityPlanRead:
    try:
        return routines.get_activity_plan(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
            references=references,
        )
    except exceptions.DailyActivityPlanError as exc:
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
    user: PlanOwner = Depends(get_current_user),
    references: PlanReferences = Depends(get_plan_references),
) -> schemas.DailyActivityPlanRead:
    try:
        return routines.prepare_activity_plan(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
            references=references,
            data=data,
        )
    except exceptions.DailyActivityPlanError as exc:
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
    user: PlanOwner = Depends(get_current_user),
    references: PlanReferences = Depends(get_plan_references),
) -> schemas.WorldCharacterRuntimeModeRead:
    try:
        return routines.update_activity_runtime_mode(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
            references=references,
            data=data,
        )
    except exceptions.DailyActivityPlanError as exc:
        _raise_plan_error(exc)
