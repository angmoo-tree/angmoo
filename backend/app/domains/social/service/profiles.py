"""Profile counts, pages, follow authorization and persistence workflows."""
from sqlalchemy.orm import Session
from app.domains.social.schemas import community as schemas
from app.domains.social.contracts.actors import SocialUser, SocialCharacter
from app.domains.social.constants import DELETED_CHARACTER_NAME
from app.domains.social.exceptions import ProfileNotFoundError, FollowSelfError
from app.domains.social.repository import profiles as profile_repository
from app.domains.social.service import notifications
from app.domains.social.service.timeline import _resolve_author_character
from app.domains.social.service.presentation import _post_summary
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.utils.limits import _safe_limit
from app.domains.identity.service import profile as identity_profile
from app.domains.characters.service import profile as character_profile


def follow_profile(
    db: Session, user: SocialUser, data: schemas.FollowCreate
) -> schemas.FollowRead:
    follower_user, follower_character = _resolve_follower(db, user, data)
    target_user, target_character = _resolve_target_profile(db, data.target_type, data.target_id)
    _ensure_not_self_follow(follower_user, follower_character, target_user, target_character)
    follow, created = profile_repository.create_follow(
        db,
        follower_user=follower_user,
        follower_character=follower_character,
        target_user=target_user,
        target_character=target_character,
    )
    if created:
        notifications.create_notification(
            db,
            notification_type="follow",
            recipient_user_id=target_user.id if target_user else None,
            recipient_character_id=target_character.id if target_character else None,
            actor_user_id=follower_user.id if follower_user else None,
            actor_character_id=follower_character.id if follower_character else None,
        )
    return schemas.FollowRead(
        follower=_profile_ref(follower_user, follower_character),
        target=_profile_ref(target_user, target_character),
        created_at=follow.created_at,
    )


def get_follow_status(
    db: Session, user: SocialUser, data: schemas.FollowCreate
) -> schemas.FollowStatusRead:
    follower_user, follower_character = _resolve_follower(db, user, data)
    target_user, target_character = _resolve_target_profile(db, data.target_type, data.target_id)
    _ensure_not_self_follow(follower_user, follower_character, target_user, target_character)
    return schemas.FollowStatusRead(
        following=profile_repository.profile_follow_exists(
            db,
            follower_user=follower_user,
            follower_character=follower_character,
            target_user=target_user,
            target_character=target_character,
        )
    )


def unfollow_profile(db: Session, user: SocialUser, data: schemas.FollowCreate) -> None:
    follower_user, follower_character = _resolve_follower(db, user, data)
    target_user, target_character = _resolve_target_profile(db, data.target_type, data.target_id)
    profile_repository.delete_follow(
        db,
        follower_user=follower_user,
        follower_character=follower_character,
        target_user=target_user,
        target_character=target_character,
    )


def get_user_profile(db: Session, user_id: str) -> schemas.ProfileRead:
    user = identity_profile.get_user(db, user_id)
    if user is None:
        raise ProfileNotFoundError(user_id)
    return schemas.ProfileRead(
        profile=_profile_ref(user, None),
        post_count=profile_repository.count_profile_posts(db, user_id=user.id),
        reply_count=profile_repository.count_profile_replies(db, user_id=user.id),
        liked_post_count=profile_repository.count_profile_likes(db, user_id=user.id),
        received_like_count=profile_repository.count_profile_received_likes(db, user_id=user.id),
        follower_count=profile_repository.count_profile_followers(db, user_id=user.id),
        user_follower_count=profile_repository.count_profile_followers(
            db, user_id=user.id, follower_type="user"
        ),
        character_follower_count=profile_repository.count_profile_followers(
            db, user_id=user.id, follower_type="character"
        ),
        following_count=profile_repository.count_profile_following(db, user_id=user.id),
    )


def get_character_profile(db: Session, character_id: str) -> schemas.ProfileRead:
    character = character_profile.get_character(db, character_id)
    if character is None:
        raise ProfileNotFoundError(character_id)
    return schemas.ProfileRead(
        profile=_profile_ref(None, character),
        execution_mode=character.execution_mode,  # type: ignore[arg-type]
        post_count=profile_repository.count_profile_posts(db, character_id=character.id),
        reply_count=profile_repository.count_profile_replies(db, character_id=character.id),
        liked_post_count=profile_repository.count_profile_likes(
            db, character_id=character.id
        ),
        received_like_count=profile_repository.count_profile_received_likes(
            db, character_id=character.id
        ),
        follower_count=profile_repository.count_profile_followers(db, character_id=character.id),
        user_follower_count=profile_repository.count_profile_followers(
            db, character_id=character.id, follower_type="user"
        ),
        character_follower_count=profile_repository.count_profile_followers(
            db, character_id=character.id, follower_type="character"
        ),
        following_count=profile_repository.count_profile_following(
            db, character_id=character.id
        ),
        one_liner=character.one_liner,
    )


def get_user_profile_feed(
    db: Session,
    user_id: str,
    *,
    limit: int = 20,
    cursor: str | None = None,
    tab: str = "posts",
) -> schemas.FeedPage:
    if identity_profile.get_user(db, user_id) is None:
        raise ProfileNotFoundError(user_id)
    safe_limit = _safe_limit(limit)
    if tab == "replies":
        posts, next_cursor = profile_repository.list_profile_posts(
            db, limit=safe_limit, cursor=cursor, author_user_id=user_id, replies=True
        )
    elif tab == "likes":
        posts, next_cursor = profile_repository.list_liked_profile_posts(
            db, limit=safe_limit, cursor=cursor, user_id=user_id
        )
    else:
        posts, next_cursor = profile_repository.list_profile_posts(
            db, limit=safe_limit, cursor=cursor, author_user_id=user_id
        )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def get_character_profile_feed(
    db: Session,
    character_id: str,
    *,
    limit: int = 20,
    cursor: str | None = None,
    tab: str = "posts",
) -> schemas.FeedPage:
    if character_profile.get_character(db, character_id) is None:
        raise ProfileNotFoundError(character_id)
    safe_limit = _safe_limit(limit)
    if tab == "replies":
        posts, next_cursor = profile_repository.list_profile_posts(
            db,
            limit=safe_limit,
            cursor=cursor,
            author_character_id=character_id,
            replies=True,
        )
    elif tab == "likes":
        posts, next_cursor = profile_repository.list_liked_profile_posts(
            db, limit=safe_limit, cursor=cursor, character_id=character_id
        )
    else:
        posts, next_cursor = profile_repository.list_profile_posts(
            db, limit=safe_limit, cursor=cursor, author_character_id=character_id
        )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def get_user_profile_connections(
    db: Session,
    user_id: str,
    *,
    tab: str = "following",
    limit: int = 10,
    cursor: str | None = None,
    viewer_user: SocialUser | None = None,
) -> schemas.ProfileListPage:
    if identity_profile.get_user(db, user_id) is None:
        raise ProfileNotFoundError(user_id)
    return _profile_connections_page(
        db,
        user_id=user_id,
        tab=tab,
        limit=limit,
        cursor=cursor,
        viewer_user=viewer_user,
    )


def get_character_profile_connections(
    db: Session,
    character_id: str,
    *,
    tab: str = "following",
    limit: int = 10,
    cursor: str | None = None,
    viewer_user: SocialUser | None = None,
) -> schemas.ProfileListPage:
    if character_profile.get_character(db, character_id) is None:
        raise ProfileNotFoundError(character_id)
    return _profile_connections_page(
        db,
        character_id=character_id,
        tab=tab,
        limit=limit,
        cursor=cursor,
        viewer_user=viewer_user,
    )


def _profile_ref(
    user: SocialUser | None, character: SocialCharacter | None
) -> schemas.ProfileRef:
    if character is not None:
        if character.deleted_at is not None:
            return schemas.ProfileRef(
                profile_type="character",
                id=character.id,
                display_name=DELETED_CHARACTER_NAME,
                handle=None,
                avatar_url=None,
                banner_url=None,
            )
        return schemas.ProfileRef(
            profile_type="character",
            id=character.id,
            display_name=character.name,
            handle=character.handle,
            avatar_url=character.avatar_url,
            banner_url=character.banner_url,
        )
    if user is None:
        raise ProfileNotFoundError("profile")
    return schemas.ProfileRef(
        profile_type="user",
        id=user.id,
        display_name=user.display_name,
    )


def _profile_connections_page(
    db: Session,
    *,
    user_id: str | None = None,
    character_id: str | None = None,
    tab: str,
    limit: int,
    cursor: str | None,
    viewer_user: SocialUser | None,
) -> schemas.ProfileListPage:
    safe_limit = _safe_limit(limit)
    if tab == "character_followers":
        rows, next_cursor = profile_repository.list_profile_followers(
            db,
            user_id=user_id,
            character_id=character_id,
            follower_type="character",
            limit=safe_limit,
            cursor=cursor,
        )
        items = [
            _profile_list_item(
                db,
                user_id=row.follower_user_id,
                character_id=row.follower_character_id,
                viewer_user=viewer_user,
            )
            for row in rows
        ]
    elif tab == "user_followers":
        rows, next_cursor = profile_repository.list_profile_followers(
            db,
            user_id=user_id,
            character_id=character_id,
            follower_type="user",
            limit=safe_limit,
            cursor=cursor,
        )
        items = [
            _profile_list_item(
                db,
                user_id=row.follower_user_id,
                character_id=row.follower_character_id,
                viewer_user=viewer_user,
            )
            for row in rows
        ]
    else:
        rows, next_cursor = profile_repository.list_profile_following(
            db,
            user_id=user_id,
            character_id=character_id,
            limit=safe_limit,
            cursor=cursor,
        )
        items = [
            _profile_list_item(
                db,
                user_id=row.target_user_id,
                character_id=row.target_character_id,
                viewer_user=viewer_user,
            )
            for row in rows
        ]
    return schemas.ProfileListPage(
        items=[item for item in items if item is not None],
        next_cursor=next_cursor,
    )


def _profile_list_item(
    db: Session,
    *,
    user_id: str | None,
    character_id: str | None,
    viewer_user: SocialUser | None,
) -> schemas.ProfileListItem | None:
    if character_id is not None:
        character = character_profile.get_character(db, character_id)
        if character is None or character.deleted_at is not None:
            return None
        return schemas.ProfileListItem(
            profile=_profile_ref(None, character),
            one_liner=character.one_liner,
            viewer_following=_viewer_follows_character(db, viewer_user, character),
        )
    if user_id is not None:
        user = identity_profile.get_user(db, user_id)
        if user is None:
            return None
        return schemas.ProfileListItem(profile=_profile_ref(user, None))
    return None


def _viewer_follows_character(
    db: Session, viewer_user: SocialUser | None, character: SocialCharacter
) -> bool:
    if viewer_user is None or character.deleted_at is not None:
        return False
    return profile_repository.profile_follow_exists(
        db,
        follower_user=viewer_user,
        follower_character=None,
        target_user=None,
        target_character=character,
    )


def _character_search_result(
    character: SocialCharacter,
) -> schemas.CharacterSearchResult:
    return schemas.CharacterSearchResult(
        id=character.id,
        name=character.name,
        handle=character.handle,
        avatar_url=character.avatar_url,
        banner_url=character.banner_url,
        one_liner=character.one_liner,
    )


def _resolve_follower(
    db: Session, user: SocialUser, data: schemas.FollowCreate
) -> tuple[SocialUser | None, SocialCharacter | None]:
    if data.follower_character_id is None:
        return user, None
    return None, _resolve_author_character(db, user, data.follower_character_id)


def _resolve_target_profile(
    db: Session, target_type: str, target_id: str
) -> tuple[SocialUser | None, SocialCharacter | None]:
    if target_type != "character":
        raise ProfileNotFoundError(target_id)
    character = character_profile.get_character(db, target_id)
    if character is None or character.deleted_at is not None:
        raise ProfileNotFoundError(target_id)
    return None, character


def _ensure_not_self_follow(
    follower_user: SocialUser | None,
    follower_character: SocialCharacter | None,
    target_user: SocialUser | None,
    target_character: SocialCharacter | None,
) -> None:
    if follower_user is not None and target_user is not None:
        if follower_user.id == target_user.id:
            raise FollowSelfError("user cannot follow itself")
    if follower_character is not None and target_character is not None:
        if follower_character.id == target_character.id:
            raise FollowSelfError("character cannot follow itself")
