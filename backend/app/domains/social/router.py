"""Social HTTP endpoints; business decisions belong to the owning services."""

from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from app.domains.social.contracts.actors import SocialUser
from app.domains.social.schemas import (
    community as schemas,
    activity as activity_schemas,
)
from app.domains.social import exceptions as errors
from app.domains.social.service import (
    feed as feed_service,
    profiles as profile_service,
    posts as post_service,
)
from app.domains.social.service.timeline import (
    create_comment as disabled_comment,
    SocialTimelineService,
)
from app.domains.social.service.inbox import SocialInboxService
from app.domains.social.service.discovery import SocialDiscoveryService
from app.domains.social.service.profile_activity import ProfileActivityService
from app.domains.social.dependencies import (
    get_db,
    get_current_user,
    get_optional_current_user,
    get_timeline_service,
    get_inbox_service,
    get_discovery_service,
    get_profile_activity_service,
)

from app.api.identity_dependencies import browser_session
from app.domains.social.schemas.manual import (
    ManualSocialFeedRead,
    ManualSocialWriteRead,
    OwnerManualPostWrite,
    OwnerManualReplyWrite,
    WorldCharacterSocialProfileRead,
)
from app.domains.social.contracts.writes import (
    OwnerPostCommand,
    OwnerReplyCommand,
    SocialWriteConflictError,
    SocialWriteError,
    SocialWriteForbiddenError,
    SocialWriteNotFoundError,
    SocialWriteRetryableError,
)
from app.domains.social.contracts.profile_activity import (
    WorldCharacterSocialProfileError,
    WorldCharacterSocialProfileForbiddenError,
    WorldCharacterSocialProfileNotFoundError,
    WorldCharacterSocialProfileQuery,
    WorldCharacterSocialProfileValidationError,
)
from app.domains.social.contracts.manual_feed import ManualFeedReferences
from app.domains.social.contracts.write_execution import SocialWriteUnitOfWorkPort
from app.domains.social.service.world_profile import WorldSocialProfileService
from app.domains.social.service.manual_feed import (
    get_owner_world_post_thread,
    list_owner_world_feed,
)
from app.domains.social.dependencies import (
    get_world_profile_service,
    get_manual_feed_references,
    get_source_write_executor,
)
from app.domains.world_characters.contracts.owner_identity import (
    OwnerControlledIdentityError,
)
from app.domains.worlds import service as world_service

router = APIRouter(tags=["community"])


@router.get("/posts", response_model=list[schemas.PostSummary])
def list_posts(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[schemas.PostSummary]:
    return feed_service.list_posts(db, limit=limit)


@router.get("/feed", response_model=schemas.FeedPage)
def list_feed(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    content: schemas.FeedContentFilter = Query(default="all"),
    db: Session = Depends(get_db),
) -> schemas.FeedPage:
    return feed_service.list_feed(db, limit=limit, cursor=cursor, content=content)


@router.get("/insights/today-activity", response_model=list[schemas.TodayActivityRead])
def list_today_activity(
    limit: int = Query(default=3, ge=1, le=50),
    db: Session = Depends(get_db),
    service: SocialDiscoveryService = Depends(get_discovery_service),
) -> list[schemas.TodayActivityRead]:
    return service.list_today_activity(db, limit=limit)


@router.get("/insights/today-popular-posts", response_model=list[schemas.PostSummary])
def list_today_popular_posts(
    limit: int = Query(default=2, ge=1, le=10),
    db: Session = Depends(get_db),
) -> list[schemas.PostSummary]:
    return feed_service.list_today_popular_posts(db, limit=limit)


@router.get("/search", response_model=schemas.SearchResults)
def search_nest(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    service: SocialDiscoveryService = Depends(get_discovery_service),
) -> schemas.SearchResults:
    return service.search_nest(db, query=q, limit=limit, offset=offset)


@router.get("/feed/following", response_model=schemas.FeedPage)
def list_following_feed(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    content: schemas.FeedContentFilter = Query(default="all"),
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
) -> schemas.FeedPage:
    return feed_service.list_following_feed(
        db, user, limit=limit, cursor=cursor, content=content
    )


@router.get("/feed/following/characters/{character_id}", response_model=schemas.FeedPage)
def list_character_following_feed(
    character_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    content: schemas.FeedContentFilter = Query(default="all"),
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
) -> schemas.FeedPage:
    try:
        return feed_service.list_character_following_feed(
            db, user, character_id, limit=limit, cursor=cursor, content=content
        )
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/posts", response_model=schemas.PostDetail, status_code=status.HTTP_201_CREATED)
def create_post(
    data: schemas.PostCreate,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialTimelineService = Depends(get_timeline_service),
) -> schemas.PostDetail:
    try:
        return service.create_post(db, user, data)
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/posts/{post_id}/thread", response_model=schemas.PostThreadRead)
def get_post_thread(
    post_id: str, db: Session = Depends(get_db)
) -> schemas.PostThreadRead:
    try:
        return post_service.get_post_thread(db, post_id)
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@router.get("/posts/{post_id}", response_model=schemas.PostDetail)
def get_post(post_id: str, db: Session = Depends(get_db)) -> schemas.PostDetail:
    try:
        return post_service.get_post(db, post_id)
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: str,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialTimelineService = Depends(get_timeline_service),
) -> None:
    try:
        service.delete_post(db, user, post_id)
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return None


@router.post("/posts/{post_id}/reports", response_model=schemas.PostReportRead)
def report_post(
    post_id: str,
    data: schemas.PostReportCreate,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialTimelineService = Depends(get_timeline_service),
) -> schemas.PostReportRead:
    try:
        return service.report_post(db, user, post_id, data)
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except errors.PostReportNotAllowedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except errors.CommunityRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Community action temporarily rate limited",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


@router.post(
    "/posts/{post_id}/replies",
    response_model=schemas.PostDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_reply(
    post_id: str,
    data: schemas.TimelineReplyCreate,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialTimelineService = Depends(get_timeline_service),
) -> schemas.PostDetail:
    try:
        return service.create_reply(db, user, post_id, data)
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except errors.CommunityRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Community action temporarily rate limited",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


@router.post(
    "/posts/{post_id}/quotes",
    response_model=schemas.PostDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_quote(
    post_id: str,
    data: schemas.TimelineQuoteCreate,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialTimelineService = Depends(get_timeline_service),
) -> schemas.PostDetail:
    try:
        return service.create_quote(db, user, post_id, data)
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/posts/{post_id}/comments",
    response_model=schemas.CommentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    post_id: str, data: schemas.CommentCreate, db: Session = Depends(get_db)
) -> schemas.CommentRead:
    try:
        return disabled_comment(db, post_id, data)
    except errors.LegacyCommentsDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )


@router.post("/posts/{post_id}/likes", response_model=schemas.PostDetail)
def like_post(
    post_id: str,
    data: schemas.PostLikeCreate,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialTimelineService = Depends(get_timeline_service),
) -> schemas.PostDetail:
    try:
        return service.like_post(db, user, post_id, data)
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete("/posts/{post_id}/likes", response_model=schemas.PostDetail)
def unlike_post(
    post_id: str,
    character_id: str | None = None,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialTimelineService = Depends(get_timeline_service),
) -> schemas.PostDetail:
    try:
        return service.unlike_post(
            db, user, post_id, schemas.PostLikeCreate(character_id=character_id)
        )
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/posts/{post_id}/reposts", response_model=schemas.PostDetail)
def repost_post(
    post_id: str,
    data: schemas.PostLikeCreate,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialTimelineService = Depends(get_timeline_service),
) -> schemas.PostDetail:
    try:
        return service.repost_post(db, user, post_id, data)
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete("/posts/{post_id}/reposts", response_model=schemas.PostDetail)
def unrepost_post(
    post_id: str,
    character_id: str | None = None,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialTimelineService = Depends(get_timeline_service),
) -> schemas.PostDetail:
    try:
        return service.unrepost_post(
            db, user, post_id, schemas.PostLikeCreate(character_id=character_id)
        )
    except errors.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/profiles/users/{user_id}", response_model=schemas.ProfileRead)
def get_user_profile(
    user_id: str, db: Session = Depends(get_db)
) -> schemas.ProfileRead:
    try:
        return profile_service.get_user_profile(db, user_id)
    except errors.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get("/profiles/users/{user_id}/feed", response_model=schemas.FeedPage)
def get_user_profile_feed(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    tab: Literal["posts", "replies", "likes"] = "posts",
    db: Session = Depends(get_db),
) -> schemas.FeedPage:
    try:
        return profile_service.get_user_profile_feed(
            db, user_id, limit=limit, cursor=cursor, tab=tab
        )
    except errors.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get("/profiles/users/{user_id}/connections", response_model=schemas.ProfileListPage)
def get_user_profile_connections(
    user_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    cursor: str | None = None,
    tab: Literal["following", "character_followers", "user_followers"] = "following",
    db: Session = Depends(get_db),
    viewer_user: SocialUser | None = Depends(get_optional_current_user),
) -> schemas.ProfileListPage:
    try:
        return profile_service.get_user_profile_connections(
            db, user_id, tab=tab, limit=limit, cursor=cursor, viewer_user=viewer_user
        )
    except errors.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get("/profiles/characters/{character_id}", response_model=schemas.ProfileRead)
def get_character_profile(
    character_id: str, db: Session = Depends(get_db)
) -> schemas.ProfileRead:
    try:
        return profile_service.get_character_profile(db, character_id)
    except errors.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get("/profiles/characters/{character_id}/feed", response_model=schemas.FeedPage)
def get_character_profile_feed(
    character_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    tab: Literal["posts", "replies", "likes"] = "posts",
    db: Session = Depends(get_db),
) -> schemas.FeedPage:
    try:
        return profile_service.get_character_profile_feed(
            db, character_id, limit=limit, cursor=cursor, tab=tab
        )
    except errors.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get(
    "/profiles/characters/{character_id}/connections",
    response_model=schemas.ProfileListPage,
)
def get_character_profile_connections(
    character_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    cursor: str | None = None,
    tab: Literal["following", "character_followers", "user_followers"] = "following",
    db: Session = Depends(get_db),
    viewer_user: SocialUser | None = Depends(get_optional_current_user),
) -> schemas.ProfileListPage:
    try:
        return profile_service.get_character_profile_connections(
            db,
            character_id,
            tab=tab,
            limit=limit,
            cursor=cursor,
            viewer_user=viewer_user,
        )
    except errors.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get("/profiles/follows/status", response_model=schemas.FollowStatusRead)
def get_follow_status(
    target_type: Literal["character"],
    target_id: str = Query(min_length=1, max_length=64),
    follower_character_id: str | None = None,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
) -> schemas.FollowStatusRead:
    try:
        return profile_service.get_follow_status(
            db,
            user,
            schemas.FollowCreate(
                target_type=target_type,
                target_id=target_id,
                follower_character_id=follower_character_id,
            ),
        )
    except errors.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except errors.FollowSelfError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/profiles/follows",
    response_model=schemas.FollowRead,
    status_code=status.HTTP_201_CREATED,
)
def follow_profile(
    data: schemas.FollowCreate,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
) -> schemas.FollowRead:
    try:
        return profile_service.follow_profile(db, user, data)
    except errors.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except errors.FollowSelfError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/profiles/follows", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_profile(
    data: schemas.FollowCreate,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
) -> None:
    try:
        profile_service.unfollow_profile(db, user, data)
    except errors.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except errors.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return None


@router.get("/notifications", response_model=schemas.NotificationPage)
def list_notifications(
    limit: int = Query(default=10, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialInboxService = Depends(get_inbox_service),
) -> schemas.NotificationPage:
    return service.list_notifications(db, user, limit=limit, cursor=cursor)


@router.patch(
    "/notifications/{notification_id}/read", response_model=schemas.NotificationRead
)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: SocialUser = Depends(get_current_user),
    service: SocialInboxService = Depends(get_inbox_service),
) -> schemas.NotificationRead:
    try:
        return service.mark_notification_read(db, user, notification_id)
    except errors.NotificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )


@router.get(
    "/characters/{character_id}/activity",
    response_model=activity_schemas.CharacterActivityRead,
)
def get_character_activity(
    character_id: str, db: Session = Depends(get_db),
    service: ProfileActivityService = Depends(get_profile_activity_service),
) -> activity_schemas.CharacterActivityRead:
    try:
        return service.get_character_activity(db, character_id)
    except errors.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )


manual_router = APIRouter(prefix="/worlds", tags=["manual-social"])
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


@manual_router.get(
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
    profile_service: WorldSocialProfileService = Depends(get_world_profile_service),
) -> WorldCharacterSocialProfileRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        page = profile_service.read(
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


@manual_router.get(
    "/{world_id}/manual-social/feed",
    response_model=ManualSocialFeedRead,
)
def read_manual_social_feed(
    world_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    references: ManualFeedReferences = Depends(get_manual_feed_references),
) -> ManualSocialFeedRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return list_owner_world_feed(
            db,
            world_id=world_id,
            current_user_id=current_user.id,
            references=references,
        )
    except (SocialWriteError, OwnerControlledIdentityError) as exc:
        _raise_error(exc)
        raise AssertionError("unreachable")


@manual_router.get(
    "/{world_id}/manual-social/posts/{post_id}",
    response_model=ManualSocialFeedRead,
)
def read_manual_social_post_thread(
    world_id: str,
    post_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    references: ManualFeedReferences = Depends(get_manual_feed_references),
) -> ManualSocialFeedRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return get_owner_world_post_thread(
            db,
            world_id=world_id,
            post_id=post_id,
            current_user_id=current_user.id,
            references=references,
        )
    except (SocialWriteError, OwnerControlledIdentityError) as exc:
        _raise_error(exc)
        raise AssertionError("unreachable")


@manual_router.post(
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
    executor: SocialWriteUnitOfWorkPort = Depends(get_source_write_executor),
) -> ManualSocialWriteRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return executor.create_owner_post(
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


@manual_router.post(
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
    executor: SocialWriteUnitOfWorkPort = Depends(get_source_write_executor),
) -> ManualSocialWriteRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return executor.create_owner_reply(
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
