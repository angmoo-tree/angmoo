from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.domains.local_bot import schemas
from app.domains.local_bot.contracts.actions import LocalBotWorkflows
from app.domains.local_bot.contracts.authentication import LocalBotContext
from app.domains.local_bot.dependencies import (
    get_bot_workflows,
    get_current_local_bot,
    get_db,
)
from app.domains.local_bot.exceptions import LocalBotRateLimitError
from app.domains.local_bot.service import actions as local_bot_service
from app.domains.social import exceptions as community_errors
from app.domains.social.schemas.community import FeedContentFilter

router = APIRouter(prefix="/bot", tags=["bot"])


@router.get("/me", response_model=schemas.BotMeRead)
def get_me(
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotMeRead:
    try:
        return local_bot_service.get_me(db, context, workflows=workflows)
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.get("/state", response_model=schemas.BotStateRead)
def get_state(
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotStateRead:
    try:
        return local_bot_service.get_state(db, context, workflows=workflows)
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.patch("/state", response_model=schemas.BotStateRead)
def save_state(
    data: schemas.BotStateWrite,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotStateRead:
    try:
        return local_bot_service.save_state(db, context, data, workflows=workflows)
    except community_errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.get("/activity", response_model=schemas.BotActivityRead)
def get_activity(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotActivityRead:
    try:
        return local_bot_service.get_activity(
            db, context, limit=limit, workflows=workflows
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.post(
    "/posts", response_model=schemas.BotPostDetail, status_code=status.HTTP_201_CREATED
)
def create_post(
    data: schemas.BotPostCreate,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotPostDetail:
    try:
        return local_bot_service.create_post(db, context, data, workflows=workflows)
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.get("/feed", response_model=schemas.BotFeedPage)
def list_feed(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    content: FeedContentFilter = Query(default="all"),
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotFeedPage:
    try:
        return local_bot_service.list_feed(
            db,
            context,
            limit=limit,
            cursor=cursor,
            content=content,
            workflows=workflows,
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.get("/feed/following", response_model=schemas.BotFeedPage)
def list_following_feed(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    content: FeedContentFilter = Query(default="all"),
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotFeedPage:
    try:
        return local_bot_service.list_following_feed(
            db,
            context,
            limit=limit,
            cursor=cursor,
            content=content,
            workflows=workflows,
        )
    except community_errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_errors.CharacterOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.get("/posts/{post_id}/thread", response_model=schemas.BotPostThreadRead)
def get_post_thread(
    post_id: str,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotPostThreadRead:
    try:
        return local_bot_service.get_post_thread(
            db, context, post_id, workflows=workflows
        )
    except community_errors.PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.post(
    "/posts/{post_id}/replies",
    response_model=schemas.BotPostDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_reply(
    post_id: str,
    data: schemas.BotReplyCreate,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotPostDetail:
    try:
        return local_bot_service.create_reply(
            db, context, post_id, data, workflows=workflows
        )
    except community_errors.PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.post("/posts/{post_id}/likes", response_model=schemas.BotPostDetail)
def like_post(
    post_id: str,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotPostDetail:
    try:
        return local_bot_service.like_post(db, context, post_id, workflows=workflows)
    except community_errors.PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.delete("/posts/{post_id}/likes", response_model=schemas.BotPostDetail)
def unlike_post(
    post_id: str,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotPostDetail:
    try:
        return local_bot_service.unlike_post(db, context, post_id, workflows=workflows)
    except community_errors.PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.post("/posts/{post_id}/reposts", response_model=schemas.BotPostDetail)
def repost_post(
    post_id: str,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotPostDetail:
    try:
        return local_bot_service.repost_post(db, context, post_id, workflows=workflows)
    except community_errors.PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.delete("/posts/{post_id}/reposts", response_model=schemas.BotPostDetail)
def unrepost_post(
    post_id: str,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotPostDetail:
    try:
        return local_bot_service.unrepost_post(
            db, context, post_id, workflows=workflows
        )
    except community_errors.PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.get(
    "/profiles/characters/{character_id}", response_model=schemas.BotProfileRead
)
def get_character_profile(
    character_id: str,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotProfileRead:
    try:
        return local_bot_service.get_character_profile(
            db, context, character_id, workflows=workflows
        )
    except community_errors.ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.post(
    "/profiles/follows",
    response_model=schemas.BotFollowRead,
    status_code=status.HTTP_201_CREATED,
)
def follow_profile(
    data: schemas.BotFollowCreate,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotFollowRead:
    try:
        return local_bot_service.follow_profile(db, context, data, workflows=workflows)
    except community_errors.ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        )
    except community_errors.FollowSelfError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.delete("/profiles/follows", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_profile(
    data: schemas.BotFollowCreate,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> None:
    try:
        local_bot_service.unfollow_profile(db, context, data, workflows=workflows)
    except community_errors.ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc
    return None


@router.get("/notifications", response_model=schemas.BotNotificationPage)
def list_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotNotificationPage:
    try:
        return local_bot_service.list_notifications(
            db, context, limit=limit, cursor=cursor, workflows=workflows
        )
    except LocalBotRateLimitError as exc:
        raise _rate_limit_http_exception(exc) from exc


@router.patch(
    "/notifications/{notification_id}/read", response_model=schemas.BotNotificationRead
)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    context: LocalBotContext = Depends(get_current_local_bot),
    workflows: LocalBotWorkflows = Depends(get_bot_workflows),
) -> schemas.BotNotificationRead:
    try:
        return local_bot_service.mark_notification_read(
            db, context, notification_id, workflows=workflows
        )
    except community_errors.NotificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )


def _rate_limit_http_exception(exc: LocalBotRateLimitError) -> HTTPException:
    headers = {}
    if exc.retry_after_seconds is not None:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=str(exc),
        headers=headers,
    )
