from app.domains.characters.router import save_character_state, state_router
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.domains.identity.dependencies import get_current_user
from app.core.db import get_db
from app.domains.identity.dependencies import get_optional_current_user
from app.services import community as community_service

router = APIRouter(tags=["community"])


@router.get("/posts", response_model=list[schemas.PostSummary])
def list_posts(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[schemas.PostSummary]:
    return community_service.list_posts(db, limit=limit)


@router.get("/feed", response_model=schemas.FeedPage)
def list_feed(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    content: schemas.FeedContentFilter = Query(default="all"),
    db: Session = Depends(get_db),
) -> schemas.FeedPage:
    return community_service.list_feed(db, limit=limit, cursor=cursor, content=content)


@router.get("/insights/today-activity", response_model=list[schemas.TodayActivityRead])
def list_today_activity(
    limit: int = Query(default=3, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[schemas.TodayActivityRead]:
    return community_service.list_today_activity(db, limit=limit)


@router.get("/insights/today-popular-posts", response_model=list[schemas.PostSummary])
def list_today_popular_posts(
    limit: int = Query(default=2, ge=1, le=10),
    db: Session = Depends(get_db),
) -> list[schemas.PostSummary]:
    return community_service.list_today_popular_posts(db, limit=limit)


@router.get("/search", response_model=schemas.SearchResults)
def search_nest(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> schemas.SearchResults:
    return community_service.search_nest(db, query=q, limit=limit, offset=offset)


@router.get("/feed/following", response_model=schemas.FeedPage)
def list_following_feed(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    content: schemas.FeedContentFilter = Query(default="all"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.FeedPage:
    return community_service.list_following_feed(
        db, user, limit=limit, cursor=cursor, content=content
    )


@router.get("/feed/following/characters/{character_id}", response_model=schemas.FeedPage)
def list_character_following_feed(
    character_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    content: schemas.FeedContentFilter = Query(default="all"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.FeedPage:
    try:
        return community_service.list_character_following_feed(
            db, user, character_id, limit=limit, cursor=cursor, content=content
        )
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/posts", response_model=schemas.PostDetail, status_code=status.HTTP_201_CREATED)
def create_post(
    data: schemas.PostCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.PostDetail:
    try:
        return community_service.create_post(db, user, data)
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/posts/{post_id}/thread", response_model=schemas.PostThreadRead)
def get_post_thread(
    post_id: str, db: Session = Depends(get_db)
) -> schemas.PostThreadRead:
    try:
        return community_service.get_post_thread(db, post_id)
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@router.get("/posts/{post_id}", response_model=schemas.PostDetail)
def get_post(post_id: str, db: Session = Depends(get_db)) -> schemas.PostDetail:
    try:
        return community_service.get_post(db, post_id)
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> None:
    try:
        community_service.delete_post(db, user, post_id)
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return None


@router.post("/posts/{post_id}/reports", response_model=schemas.PostReportRead)
def report_post(
    post_id: str,
    data: schemas.PostReportCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.PostReportRead:
    try:
        return community_service.report_post(db, user, post_id, data)
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except community_service.PostReportNotAllowedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except community_service.CommunityRateLimitedError as exc:
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
    user: models.User = Depends(get_current_user),
) -> schemas.PostDetail:
    try:
        return community_service.create_reply(db, user, post_id, data)
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except community_service.CommunityRateLimitedError as exc:
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
    user: models.User = Depends(get_current_user),
) -> schemas.PostDetail:
    try:
        return community_service.create_quote(db, user, post_id, data)
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
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
        return community_service.create_comment(db, post_id, data)
    except community_service.LegacyCommentsDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )


@router.post("/posts/{post_id}/likes", response_model=schemas.PostDetail)
def like_post(
    post_id: str,
    data: schemas.PostLikeCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.PostDetail:
    try:
        return community_service.like_post(db, user, post_id, data)
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete("/posts/{post_id}/likes", response_model=schemas.PostDetail)
def unlike_post(
    post_id: str,
    character_id: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.PostDetail:
    try:
        return community_service.unlike_post(
            db, user, post_id, schemas.PostLikeCreate(character_id=character_id)
        )
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/posts/{post_id}/reposts", response_model=schemas.PostDetail)
def repost_post(
    post_id: str,
    data: schemas.PostLikeCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.PostDetail:
    try:
        return community_service.repost_post(db, user, post_id, data)
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete("/posts/{post_id}/reposts", response_model=schemas.PostDetail)
def unrepost_post(
    post_id: str,
    character_id: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.PostDetail:
    try:
        return community_service.unrepost_post(
            db, user, post_id, schemas.PostLikeCreate(character_id=character_id)
        )
    except community_service.PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/profiles/users/{user_id}", response_model=schemas.ProfileRead)
def get_user_profile(
    user_id: str, db: Session = Depends(get_db)
) -> schemas.ProfileRead:
    try:
        return community_service.get_user_profile(db, user_id)
    except community_service.ProfileNotFoundError:
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
        return community_service.get_user_profile_feed(
            db, user_id, limit=limit, cursor=cursor, tab=tab
        )
    except community_service.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get("/profiles/users/{user_id}/connections", response_model=schemas.ProfileListPage)
def get_user_profile_connections(
    user_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    cursor: str | None = None,
    tab: Literal["following", "character_followers", "user_followers"] = "following",
    db: Session = Depends(get_db),
    viewer_user: models.User | None = Depends(get_optional_current_user),
) -> schemas.ProfileListPage:
    try:
        return community_service.get_user_profile_connections(
            db, user_id, tab=tab, limit=limit, cursor=cursor, viewer_user=viewer_user
        )
    except community_service.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get("/profiles/characters/{character_id}", response_model=schemas.ProfileRead)
def get_character_profile(
    character_id: str, db: Session = Depends(get_db)
) -> schemas.ProfileRead:
    try:
        return community_service.get_character_profile(db, character_id)
    except community_service.ProfileNotFoundError:
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
        return community_service.get_character_profile_feed(
            db, character_id, limit=limit, cursor=cursor, tab=tab
        )
    except community_service.ProfileNotFoundError:
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
    viewer_user: models.User | None = Depends(get_optional_current_user),
) -> schemas.ProfileListPage:
    try:
        return community_service.get_character_profile_connections(
            db,
            character_id,
            tab=tab,
            limit=limit,
            cursor=cursor,
            viewer_user=viewer_user,
        )
    except community_service.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get("/profiles/follows/status", response_model=schemas.FollowStatusRead)
def get_follow_status(
    target_type: Literal["character"],
    target_id: str = Query(min_length=1, max_length=64),
    follower_character_id: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.FollowStatusRead:
    try:
        return community_service.get_follow_status(
            db,
            user,
            schemas.FollowCreate(
                target_type=target_type,
                target_id=target_id,
                follower_character_id=follower_character_id,
            ),
        )
    except community_service.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except community_service.FollowSelfError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/profiles/follows",
    response_model=schemas.FollowRead,
    status_code=status.HTTP_201_CREATED,
)
def follow_profile(
    data: schemas.FollowCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.FollowRead:
    try:
        return community_service.follow_profile(db, user, data)
    except community_service.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except community_service.FollowSelfError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/profiles/follows", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_profile(
    data: schemas.FollowCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> None:
    try:
        community_service.unfollow_profile(db, user, data)
    except community_service.ProfileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return None


@router.get("/notifications", response_model=schemas.NotificationPage)
def list_notifications(
    limit: int = Query(default=10, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.NotificationPage:
    return community_service.list_notifications(db, user, limit=limit, cursor=cursor)


@router.patch(
    "/notifications/{notification_id}/read", response_model=schemas.NotificationRead
)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.NotificationRead:
    try:
        return community_service.mark_notification_read(db, user, notification_id)
    except community_service.NotificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )


router.routes.extend(state_router.routes)


@router.get(
    "/characters/{character_id}/activity",
    response_model=schemas.CharacterActivityRead,
)
def get_character_activity(
    character_id: str, db: Session = Depends(get_db)
) -> schemas.CharacterActivityRead:
    try:
        return community_service.get_character_activity(db, character_id)
    except community_service.CharacterNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
