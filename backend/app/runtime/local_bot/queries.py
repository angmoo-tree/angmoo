"""Original LocalBot projections across Social, Routines and Character owners.

Every read uses the caller Session. Synthetic non-Session fallbacks and each
query's original predicates, limits and return shape are intentionally retained.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.characters.models import CharacterState
from app.domains.local_bot.constants import (
    POST_COOLDOWN,
    RATE_LIMIT_LOG_DEDUPE_WINDOW,
    REACTION_ACTION_TYPES,
)
from app.domains.local_bot.contracts.authentication import LocalBotContext
from app.domains.routines.models.resident import AgentActivityLog
from app.domains.social.models.posts import Post, PostLike, PostRepost, ProfileFollow


def read_character_state(
    db: Session, context: LocalBotContext
) -> CharacterState | None:
    return db.get(CharacterState, context.character.id)


def list_activity(
    db: Session, context: LocalBotContext, *, limit: int
) -> list[AgentActivityLog]:
    return db.scalars(
        select(AgentActivityLog)
        .where(AgentActivityLog.character_id == context.character.id)
        .order_by(AgentActivityLog.created_at.desc())
        .limit(limit)
    ).all()


def recent_root_post_at(
    db: Session, context: LocalBotContext, *, now: datetime
) -> datetime | None:
    return db.scalar(
        select(Post.created_at)
        .where(Post.author_character_id == context.character.id)
        .where(Post.post_type == "post")
        .where(Post.deleted_at.is_(None))
        .where(Post.created_at >= now - POST_COOLDOWN)
        .order_by(Post.created_at.desc())
        .limit(1)
    )


def count_root_posts_since(
    db: Session, context: LocalBotContext, *, day_start: datetime
) -> int | None:
    return db.scalar(
        select(func.count(Post.id))
        .where(Post.author_character_id == context.character.id)
        .where(Post.post_type == "post")
        .where(Post.deleted_at.is_(None))
        .where(Post.created_at >= day_start)
    )


def latest_root_post_at(db: Session, context: LocalBotContext) -> datetime | None:
    return db.scalar(
        select(Post.created_at)
        .where(Post.author_character_id == context.character.id)
        .where(Post.post_type == "post")
        .where(Post.deleted_at.is_(None))
        .order_by(Post.created_at.desc())
        .limit(1)
    )


def root_post_usage_since(
    db: Session, context: LocalBotContext, *, day_start: datetime
) -> int | None:
    return db.scalar(
        select(func.count(Post.id))
        .where(Post.author_character_id == context.character.id)
        .where(Post.post_type == "post")
        .where(Post.deleted_at.is_(None))
        .where(Post.created_at >= day_start)
    )


def reaction_usage_since(
    db: Session, context: LocalBotContext, *, day_start: datetime
) -> int | None:
    return db.scalar(
        select(func.count(AgentActivityLog.id))
        .where(AgentActivityLog.character_id == context.character.id)
        .where(AgentActivityLog.action_type.in_(REACTION_ACTION_TYPES))
        .where(AgentActivityLog.created_at >= day_start)
    )


def recent_activity_at(
    db: Session,
    context: LocalBotContext,
    *,
    action_types: tuple[str, ...],
    now: datetime,
    cooldown: timedelta,
) -> datetime | None:
    return db.scalar(
        select(AgentActivityLog.created_at)
        .where(AgentActivityLog.character_id == context.character.id)
        .where(AgentActivityLog.action_type.in_(action_types))
        .where(AgentActivityLog.created_at >= now - cooldown)
        .order_by(AgentActivityLog.created_at.desc())
        .limit(1)
    )


def activity_usage_since(
    db: Session,
    context: LocalBotContext,
    *,
    action_types: tuple[str, ...],
    day_start: datetime,
) -> int | None:
    return db.scalar(
        select(func.count(AgentActivityLog.id))
        .where(AgentActivityLog.character_id == context.character.id)
        .where(AgentActivityLog.action_type.in_(action_types))
        .where(AgentActivityLog.created_at >= day_start)
    )


def recent_rate_limit_log_id(
    db: Session, context: LocalBotContext, *, now: datetime, label: str
) -> int | None:
    return db.scalar(
        select(AgentActivityLog.id)
        .where(AgentActivityLog.character_id == context.character.id)
        .where(AgentActivityLog.action_type == "local_bot_rate_limited")
        .where(AgentActivityLog.created_at >= now - RATE_LIMIT_LOG_DEDUPE_WINDOW)
        .where(AgentActivityLog.result.like(f"label={label};%"))
        .order_by(AgentActivityLog.created_at.desc())
        .limit(1)
    )


def _latest_activity_at(
    db: Session, context: LocalBotContext, *, action_types: tuple[str, ...]
) -> datetime | None:
    return db.scalar(
        select(AgentActivityLog.created_at)
        .where(AgentActivityLog.character_id == context.character.id)
        .where(AgentActivityLog.action_type.in_(action_types))
        .order_by(AgentActivityLog.created_at.desc())
        .limit(1)
    )


def _count_activities_today(
    db: Session,
    context: LocalBotContext,
    *,
    action_types: tuple[str, ...],
    day_start: datetime,
) -> int:
    return (
        db.scalar(
            select(func.count(AgentActivityLog.id))
            .where(AgentActivityLog.character_id == context.character.id)
            .where(AgentActivityLog.action_type.in_(action_types))
            .where(AgentActivityLog.created_at >= day_start)
        )
        or 0
    )


def _post_like_exists(db: Session, context: LocalBotContext, post_id: str) -> bool:
    if not isinstance(db, Session):
        return False
    return (
        db.scalar(
            select(PostLike.id).where(
                PostLike.post_id == post_id,
                PostLike.character_id == context.character.id,
            )
        )
        is not None
    )


def _post_repost_exists(db: Session, context: LocalBotContext, post_id: str) -> bool:
    if not isinstance(db, Session):
        return False
    return (
        db.scalar(
            select(PostRepost.id).where(
                PostRepost.post_id == post_id,
                PostRepost.character_id == context.character.id,
            )
        )
        is not None
    )


def _profile_follow_exists(
    db: Session, context: LocalBotContext, target_character_id: str
) -> bool:
    if not isinstance(db, Session):
        return False
    return (
        db.scalar(
            select(ProfileFollow.id).where(
                ProfileFollow.follower_user_id.is_(None),
                ProfileFollow.follower_character_id == context.character.id,
                ProfileFollow.target_user_id.is_(None),
                ProfileFollow.target_character_id == target_character_id,
            )
        )
        is not None
    )
