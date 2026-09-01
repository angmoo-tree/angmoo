from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core import browser_session
from app.core.db import get_db
from app.domains.social.api.schemas import (
    ManualSocialFeedRead,
    ManualSocialWriteRead,
    OwnerManualPostWrite,
    OwnerManualReplyWrite,
    WorldCharacterSocialProfileRead,
)
from app.domains.social.public import (
    OwnerPostCommand,
    OwnerReplyCommand,
    SocialWriteConflictError,
    SocialWriteError,
    SocialWriteForbiddenError,
    SocialWriteNotFoundError,
    SocialWriteRetryableError,
    WorldCharacterSocialProfileError,
    WorldCharacterSocialProfileForbiddenError,
    WorldCharacterSocialProfileNotFoundError,
    WorldCharacterSocialProfileQuery,
    WorldCharacterSocialProfileValidationError,
    create_owner_post,
    create_owner_reply,
    read_world_character_social_profile,
)
from app.domains.world_characters.public import (
    OwnerControlledIdentityError,
)
from app.domains.worlds import public as world_service
from app.runtime.social.sqlalchemy_profile_repository import (
    SqlAlchemyWorldCharacterSocialProfileReader,
)
from app.runtime.social.sqlalchemy_read_repository import (
    get_owner_world_post_thread,
    list_owner_world_feed,
)
from app.runtime.social.sqlalchemy_unit_of_work import (
    SqlAlchemySocialWriteUnitOfWork,
)

router = APIRouter(prefix="/worlds", tags=["manual-social"])
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
]


def _raise_error(exc: Exception) -> None:
    reason = getattr(exc, "reason_code", "manual_social_error")
    if isinstance(
        exc,
        (
            SocialWriteNotFoundError,
            WorldCharacterSocialProfileNotFoundError,
            world_service.WorldNotFoundError,
        ),
    ):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(
        exc,
        (
            SocialWriteForbiddenError,
            WorldCharacterSocialProfileForbiddenError,
            OwnerControlledIdentityError,
            world_service.WorldMembershipRequiredError,
            world_service.WorldCreatorRoleRequiredError,
        ),
    ):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, WorldCharacterSocialProfileValidationError):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(exc, world_service.WorldArchivedError) or isinstance(
        exc, SocialWriteConflictError
    ):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, SocialWriteRetryableError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=reason) from exc


@router.get(
    "/{world_id}/world-characters/{world_character_id}/social-profile",
    response_model=WorldCharacterSocialProfileRead,
)
def read_world_character_social_activity(
    world_id: str,
    world_character_id: str,
    request: Request,
    tab: Literal["posts", "replies", "likes"] = Query("posts"),
    limit: int = Query(10, ge=1, le=20),
    cursor: str | None = Query(None, min_length=1, max_length=2048),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WorldCharacterSocialProfileRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        page = read_world_character_social_profile(
            SqlAlchemyWorldCharacterSocialProfileReader(db),
            WorldCharacterSocialProfileQuery(
                world_id=world_id,
                world_character_id=world_character_id,
                current_user_id=str(current_user.id),
                tab=tab,
                limit=limit,
                cursor=cursor,
            ),
        )
    except (WorldCharacterSocialProfileError, world_service.WorldServiceError) as exc:
        _raise_error(exc)
        raise AssertionError("unreachable")
    return WorldCharacterSocialProfileRead.from_snapshot(page)


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
    except (SocialWriteError, OwnerControlledIdentityError) as exc:
        _raise_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/{world_id}/manual-social/posts/{post_id}",
    response_model=ManualSocialFeedRead,
)
def read_manual_social_post_thread(
    world_id: str,
    post_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ManualSocialFeedRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return get_owner_world_post_thread(
            db,
            world_id=world_id,
            post_id=post_id,
            current_user_id=current_user.id,
        )
    except (SocialWriteError, OwnerControlledIdentityError) as exc:
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
            SqlAlchemySocialWriteUnitOfWork(db),
            OwnerPostCommand(
                world_id=world_id,
                current_user_id=str(current_user.id),
                idempotency_key=idempotency_key.strip(),
                title=data.title,
                body=data.body,
            ),
        )
    except (SocialWriteError, OwnerControlledIdentityError) as exc:
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
            SqlAlchemySocialWriteUnitOfWork(db),
            OwnerReplyCommand(
                world_id=world_id,
                target_post_id=post_id,
                current_user_id=str(current_user.id),
                idempotency_key=idempotency_key.strip(),
                body=data.body,
            ),
        )
    except (SocialWriteError, OwnerControlledIdentityError) as exc:
        _raise_error(exc)
        raise AssertionError("unreachable")


__all__ = ["router"]
