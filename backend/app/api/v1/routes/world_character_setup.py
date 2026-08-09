from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import get_current_user, get_db
from app.services import world_character_setup


router = APIRouter(prefix="/world-characters", tags=["world-character-setup"])


def _raise_setup_error(exc: world_character_setup.WorldCharacterSetupError) -> None:
    if isinstance(exc, world_character_setup.WorldCharacterSetupNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, world_character_setup.WorldCharacterSetupForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, world_character_setup.WorldCharacterSetupConflictError):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc


@router.get(
    "/{world_character_id}/autonomy-setup",
    response_model=schemas.WorldCharacterSetupRead,
)
def get_autonomy_setup(
    world_character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return world_character_setup.get_setup(
            db, world_character_id=world_character_id, user=user
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/preflight",
    response_model=schemas.WorldCharacterSetupPreflightRead,
)
def preflight_autonomy_setup(
    world_character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterSetupPreflightRead:
    try:
        return world_character_setup.preflight_setup(
            db, world_character_id=world_character_id, user=user
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/generate",
    response_model=schemas.WorldCharacterSetupRead,
)
async def generate_autonomy_setup(
    world_character_id: str,
    data: schemas.WorldCharacterSetupGenerateCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return await world_character_setup.generate_setup(
            db,
            world_character_id=world_character_id,
            user=user,
            data=data,
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/retry",
    response_model=schemas.WorldCharacterSetupRead,
)
async def retry_autonomy_setup(
    world_character_id: str,
    data: schemas.WorldCharacterSetupRetryCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return await world_character_setup.retry_setup(
            db,
            world_character_id=world_character_id,
            user=user,
            data=data,
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/approve",
    response_model=schemas.WorldCharacterSetupRead,
)
def approve_autonomy_setup(
    world_character_id: str,
    data: schemas.WorldCharacterSetupApproveCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return world_character_setup.approve_setup(
            db,
            world_character_id=world_character_id,
            user=user,
            data=data,
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/reject",
    response_model=schemas.WorldCharacterSetupRead,
)
def reject_autonomy_setup(
    world_character_id: str,
    data: schemas.WorldCharacterSetupRejectCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return world_character_setup.reject_setup(
            db,
            world_character_id=world_character_id,
            user=user,
            data=data,
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)
