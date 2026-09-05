from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.domains.world_characters.schemas import setup as schemas
from app.api.identity_dependencies import get_current_user
from app.core.db import get_db
from app.api.identity_dependencies import browser_session
from app.domains.world_characters.service import autonomous_setup as world_character_setup
from app.domains.world_characters import exceptions as wc_errors
from app.domains.worlds import service as world_service
from app.api.world_errors import _raise_world_error
from app.api.world_character_dependencies import leave_service


router = APIRouter(prefix="/worlds", tags=["worlds"])




def _raise_world_character_error(exc: world_character_setup.WorldCharacterSetupError) -> None:
    if isinstance(exc, world_character_setup.WorldCharacterSetupNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, world_character_setup.WorldCharacterSetupForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, world_character_setup.WorldCharacterSetupConflictError):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc


def _raise_world_character_lifecycle_error(
    exc: wc_errors.StudioWorldCharacterLifecycleError,
) -> None:
    if isinstance(exc, wc_errors.StudioWorldCharacterNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, wc_errors.StudioWorldCharacterForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(
        exc,
        (
            wc_errors.StudioWorldCharacterBusyError,
            wc_errors.StudioWorldCharacterConflictError,
        ),
    ):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc


@router.get(
    "/{world_id}/characters/{character_id}",
    response_model=schemas.WorldCharacterEntryRead,
)
def get_world_character_entry(
    world_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
) -> schemas.WorldCharacterEntryRead:
    try:
        return world_character_setup.get_world_entry(
            db,
            world_id=world_id,
            character_id=character_id,
            user=user,
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_world_character_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/characters",
    response_model=schemas.WorldCharacterEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def enter_world_with_character(
    world_id: str,
    data: schemas.WorldCharacterEntryCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
) -> schemas.WorldCharacterEntryRead:
    try:
        return world_character_setup.enter_world(
            db,
            world_id=world_id,
            user=user,
            data=data,
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_world_character_error(exc)
        raise AssertionError("unreachable")


@router.patch(
    "/{world_id}/characters/{character_id}/role",
    response_model=schemas.WorldCharacterEntryRead,
)
def update_world_character_role(
    world_id: str,
    character_id: str,
    data: schemas.WorldCharacterRoleUpdate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
) -> schemas.WorldCharacterEntryRead:
    try:
        return world_character_setup.update_world_character_role(
            db,
            world_id=world_id,
            character_id=character_id,
            user=user,
            data=data,
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_world_character_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/characters/{character_id}/leave",
    response_model=schemas.WorldCharacterLeaveRead,
)
def leave_world_with_character(
    world_id: str,
    character_id: str,
    data: schemas.WorldCharacterLeaveCreate,
    request: Request,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
) -> schemas.WorldCharacterLeaveRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        result = leave_service(db).leave(
            world_id=world_id,
            character_id=character_id,
            current_user_id=user.id,
            world_character_id=data.world_character_id,
            expected_version=data.version,
            confirmation_name=data.confirmation_name,
            idempotency_key=data.idempotency_key,
        )
    except wc_errors.StudioWorldCharacterLifecycleError as exc:
        _raise_world_character_lifecycle_error(exc)
        raise AssertionError("unreachable")
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")
    return schemas.WorldCharacterLeaveRead.model_validate(result)
