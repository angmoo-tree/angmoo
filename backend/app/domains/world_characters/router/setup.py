from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.domains.world_characters.schemas import setup as schemas
from app.api.identity_dependencies import get_current_user
from app.core.db import get_db
from app.domains.world_characters.service import autonomous_setup as world_character_setup
from app.domains.world_characters import exceptions as wc_errors


router = APIRouter(prefix="/world-characters", tags=["world-character-setup"])




def _raise_setup_error(exc: wc_errors.WorldCharacterSetupError) -> None:
    if isinstance(exc, wc_errors.WorldCharacterSetupNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, wc_errors.WorldCharacterSetupForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, wc_errors.WorldCharacterSetupConflictError):
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
    user = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return world_character_setup.get_setup(
            db, world_character_id=world_character_id, user=user
        )
    except wc_errors.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/preflight",
    response_model=schemas.WorldCharacterSetupPreflightRead,
)
def preflight_autonomy_setup(
    world_character_id: str,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
) -> schemas.WorldCharacterSetupPreflightRead:
    try:
        return world_character_setup.preflight_setup(
            db, world_character_id=world_character_id, user=user
        )
    except wc_errors.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/generate",
    response_model=schemas.WorldCharacterSetupRead,
)
async def generate_autonomy_setup(
    world_character_id: str,
    data: schemas.WorldCharacterSetupGenerateCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return await world_character_setup.generate_setup(
            db,
            world_character_id=world_character_id,
            user=user,
            data=data,
        )
    except wc_errors.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/retry",
    response_model=schemas.WorldCharacterSetupRead,
)
async def retry_autonomy_setup(
    world_character_id: str,
    data: schemas.WorldCharacterSetupRetryCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return await world_character_setup.retry_setup(
            db,
            world_character_id=world_character_id,
            user=user,
            data=data,
        )
    except wc_errors.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/approve",
    response_model=schemas.WorldCharacterSetupRead,
)
def approve_autonomy_setup(
    world_character_id: str,
    data: schemas.WorldCharacterSetupApproveCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return world_character_setup.approve_setup(
            db,
            world_character_id=world_character_id,
            user=user,
            data=data,
        )
    except wc_errors.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)


@router.post(
    "/{world_character_id}/autonomy-setup/reject",
    response_model=schemas.WorldCharacterSetupRead,
)
def reject_autonomy_setup(
    world_character_id: str,
    data: schemas.WorldCharacterSetupRejectCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
) -> schemas.WorldCharacterSetupRead:
    try:
        return world_character_setup.reject_setup(
            db,
            world_character_id=world_character_id,
            user=user,
            data=data,
        )
    except wc_errors.WorldCharacterSetupError as exc:
        _raise_setup_error(exc)
