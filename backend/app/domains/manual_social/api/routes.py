from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core import browser_session
from app.core.db import get_db
from app.domains.manual_social.api.schemas import (
    ManualSocialFeedRead,
    ManualSocialWriteRead,
    OwnerManualPostWrite,
    OwnerManualReplyWrite,
)
from app.domains.manual_social.public import (
    ManualSocialConflictError,
    ManualSocialError,
    ManualSocialForbiddenError,
    ManualSocialNotFoundError,
    create_owner_post,
    create_owner_reply,
    list_owner_world_feed,
)
from app.domains.world_characters.public import (
    OwnerControlledIdentityError,
)


router = APIRouter(prefix="/worlds", tags=["manual-social"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


def _raise_error(exc: Exception) -> None:
    reason = getattr(exc, "reason_code", "manual_social_error")
    if isinstance(exc, ManualSocialNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (ManualSocialForbiddenError, OwnerControlledIdentityError)):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, ManualSocialConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=reason) from exc


@router.get(
    "/{world_id}/manual-social/feed",
    response_model=ManualSocialFeedRead,
)
def read_manual_social_feed(
    world_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ManualSocialFeedRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return list_owner_world_feed(
            db, world_id=world_id, current_user_id=current_user.id
        )
    except (ManualSocialError, OwnerControlledIdentityError) as exc:
        _raise_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/manual-social/posts",
    response_model=ManualSocialWriteRead,
    status_code=status.HTTP_201_CREATED,
)
def write_owner_post(
    world_id: str,
    data: OwnerManualPostWrite,
    request: Request,
    idempotency_key: IdempotencyKey,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ManualSocialWriteRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return create_owner_post(
            db,
            world_id=world_id,
            current_user=current_user,
            idempotency_key=idempotency_key.strip(),
            data=data,
        )
    except (ManualSocialError, OwnerControlledIdentityError) as exc:
        _raise_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/manual-social/posts/{post_id}/replies",
    response_model=ManualSocialWriteRead,
    status_code=status.HTTP_201_CREATED,
)
def write_owner_reply(
    world_id: str,
    post_id: str,
    data: OwnerManualReplyWrite,
    request: Request,
    idempotency_key: IdempotencyKey,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ManualSocialWriteRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return create_owner_reply(
            db,
            world_id=world_id,
            target_post_id=post_id,
            current_user=current_user,
            idempotency_key=idempotency_key.strip(),
            data=data,
        )
    except (ManualSocialError, OwnerControlledIdentityError) as exc:
        _raise_error(exc)
        raise AssertionError("unreachable")


__all__ = ["router"]
