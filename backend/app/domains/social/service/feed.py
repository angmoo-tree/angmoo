"""Feed selection, owner authorization and public response composition."""
from datetime import UTC, datetime, time
from app.core import agent_activity_schedule as agent_activity_policy
from sqlalchemy.orm import Session
from app.domains.social.contracts.actors import SocialUser
from app.domains.social.schemas import community as schemas
from app.domains.social.exceptions import CharacterNotFoundError, CharacterOwnershipError
from app.domains.social.repository import posts as post_repository, profiles as profile_repository
from app.domains.social.service.presentation import _post_summary
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.utils.limits import _safe_limit
from app.domains.characters.service import profile as character_profile

def list_posts(db: Session, *, limit: int = 20) -> list[schemas.PostSummary]:
    return list_feed(db, limit=limit, content="all").items


def list_feed(
    db: Session,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: schemas.FeedContentFilter = "all",
) -> schemas.FeedPage:
    posts, next_cursor = post_repository.list_timeline_posts(
        db, limit=_safe_limit(limit), cursor=cursor, content_filter=content
    )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def list_following_feed(
    db: Session,
    user: SocialUser,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: schemas.FeedContentFilter = "all",
) -> schemas.FeedPage:
    followed_user_ids, followed_character_ids = profile_repository.get_followed_profiles_for_user(
        db, user.id
    )
    posts, next_cursor = post_repository.list_timeline_posts(
        db,
        limit=_safe_limit(limit),
        cursor=cursor,
        content_filter=content,
        followed_user_ids=followed_user_ids,
        followed_character_ids=followed_character_ids,
    )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def list_character_following_feed(
    db: Session,
    user: SocialUser,
    character_id: str,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: schemas.FeedContentFilter = "all",
) -> schemas.FeedPage:
    character = character_profile.get_character(db, character_id)
    if character is None or character.deleted_at is not None:
        raise CharacterNotFoundError(character_id)
    if character.owner_id != user.id:
        raise CharacterOwnershipError(
            f"user {user.id} cannot read following feed for character {character.id}"
        )
    followed_user_ids, followed_character_ids = (
        profile_repository.get_followed_profiles_for_character(db, character.id)
    )
    posts, next_cursor = post_repository.list_timeline_posts(
        db,
        limit=_safe_limit(limit),
        cursor=cursor,
        content_filter=content,
        followed_user_ids=followed_user_ids,
        followed_character_ids=followed_character_ids,
    )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def list_today_popular_posts(
    db: Session, *, limit: int = 2
) -> list[schemas.PostSummary]:
    day_start = _today_start_utc()
    posts = post_repository.list_today_root_posts(db, day_start=day_start)
    ranked_posts = [
        summary
        for summary in (
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        )
        if _post_reaction_score(summary) > 0
    ]
    safe_limit = max(1, min(limit, 10))
    return sorted(
        ranked_posts,
        key=lambda post: (-_post_reaction_score(post), post.created_at),
    )[:safe_limit]


def _today_start_utc() -> datetime:
    local_now = datetime.now(tz=agent_activity_policy.APP_TIMEZONE)
    return datetime.combine(
        local_now.date(), time.min, tzinfo=agent_activity_policy.APP_TIMEZONE
    ).astimezone(UTC)


def _post_reaction_score(post: schemas.PostSummary) -> int:
    return (
        post.like_count * 2
        + post.reply_count
        + post.repost_count * 2
        + post.quote_count * 2
    )
