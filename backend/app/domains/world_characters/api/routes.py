from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core import browser_session
from app.core.db import get_db
from app.domains.world_characters.api.schemas import (
    OwnerControlledIdentityRead,
    OwnerControlledProfileWrite,
    identity_read,
)
from app.domains.world_characters.application.owner_controlled_identity import (
    create_owner_controlled_identity,
    get_owner_controlled_identity,
    update_owner_controlled_identity,
)
from app.domains.world_characters.domain.owner_controlled_identity import (
    LocalOwnerRequiredError,
    OwnerControlledIdentityConflictError,
    OwnerControlledIdentityError,
    OwnerControlledIdentityNotFoundError,
    OwnerControlledRoleInvalidError,
    OwnerWorldRequiredError,
)
from app.domains.world_characters.infrastructure.sqlalchemy_owner_controlled_identity import (
    SqlAlchemyOwnerControlledIdentityRepository,
)


router = APIRouter(prefix="/worlds", tags=["world-characters"])


def _raise_identity_error(exc: OwnerControlledIdentityError) -> None:
    if isinstance(exc, OwnerControlledIdentityNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (LocalOwnerRequiredError, OwnerWorldRequiredError)):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, OwnerControlledIdentityConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, OwnerControlledRoleInvalidError):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=exc.reason_code) from exc


@router.get(
    "/{world_id}/owner-character",
    response_model=OwnerControlledIdentityRead,
)
def read_owner_character(
    world_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> OwnerControlledIdentityRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return identity_read(
            get_owner_controlled_identity(
                SqlAlchemyOwnerControlledIdentityRepository(db),
                world_id=world_id,
                current_user_id=current_user.id,
            )
        )
    except OwnerControlledIdentityError as exc:
        _raise_identity_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/owner-character",
    response_model=OwnerControlledIdentityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_owner_character(
    world_id: str,
    data: OwnerControlledProfileWrite,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> OwnerControlledIdentityRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return identity_read(
            create_owner_controlled_identity(
                SqlAlchemyOwnerControlledIdentityRepository(db),
                world_id=world_id,
                current_user_id=current_user.id,
                profile=data.domain_profile(),
            )
        )
    except OwnerControlledIdentityError as exc:
        _raise_identity_error(exc)
        raise AssertionError("unreachable")


@router.patch(
    "/{world_id}/owner-character",
    response_model=OwnerControlledIdentityRead,
)
def update_owner_character(
    world_id: str,
    data: OwnerControlledProfileWrite,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> OwnerControlledIdentityRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return identity_read(
            update_owner_controlled_identity(
                SqlAlchemyOwnerControlledIdentityRepository(db),
                world_id=world_id,
                current_user_id=current_user.id,
                profile=data.domain_profile(),
            )
        )
    except OwnerControlledIdentityError as exc:
        _raise_identity_error(exc)
        raise AssertionError("unreachable")


__all__ = ["router"]
