"""Same-Session projections from Social and Character for resident execution.

Each query retains its own visibility, author, ordering and timestamp conditions.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.characters.service import profile as character_profile
from app.domains.routines.constants import APP_TIMEZONE
from app.domains.routines.contracts.planning_context import ClipContextText
from app.domains.routines.policies.resident_clock import (
    _aware_datetime,
    _today_kst_window,
)
from app.domains.social.models.posts import Post, ProfileFollow
from app.runtime.resident.context import LangGraphResidentContext

logger = logging.getLogger("app.services.langgraph_resident")


def _topic_arc_last_post_created_at(
    ctx: LangGraphResidentContext, last_post_id: str | None
) -> datetime | None:
    if not last_post_id:
        return None
    db_get = getattr(getattr(ctx, "db", None), "get", None)
    if not callable(db_get):
        return None
    try:
        post = db_get(Post, last_post_id)
    except Exception:
        logger.debug(
            "Failed to load topic arc last post for continuity context",
            exc_info=True,
            extra={"last_post_id": last_post_id, "character_id": ctx.character.id},
        )
        return None
    if post is None or getattr(post, "author_character_id", None) != ctx.character.id:
        return None
    return _aware_datetime(getattr(post, "created_at", None))


def _target_character_following(
    ctx: LangGraphResidentContext, target_character_id: str | None
) -> bool:
    target_id = str(target_character_id or "").strip()
    if not target_id:
        return False
    return (
        ctx.db.scalar(
            select(ProfileFollow.id)
            .where(
                ProfileFollow.follower_character_id == ctx.character.id,
                ProfileFollow.target_character_id == target_id,
            )
            .limit(1)
        )
        is not None
    )


def _today_own_root_posts_for_coverage(
    ctx: LangGraphResidentContext, *, clip: ClipContextText
) -> list[dict[str, Any]]:
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return []
    current_kst = ctx.run_started_at.astimezone(APP_TIMEZONE)
    start_kst = datetime.combine(
        current_kst.date(),
        datetime.min.time(),
        tzinfo=APP_TIMEZONE,
    )
    start_utc = start_kst.astimezone(UTC)
    end_utc = ctx.run_started_at.astimezone(UTC)
    try:
        posts = list(
            db_scalars(
                select(Post)
                .where(Post.author_character_id == ctx.character.id)
                .where(Post.created_at >= start_utc)
                .where(Post.created_at <= end_utc)
                .where(Post.reply_to_post_id.is_(None))
                .where(Post.repost_of_post_id.is_(None))
                .where(Post.post_type == "post")
                .where(Post.deleted_at.is_(None))
                .where(Post.report_hidden_at.is_(None))
                .order_by(Post.created_at.desc(), Post.id.desc())
                .limit(20)
            )
        )
    except Exception:
        logger.debug(
            "Failed to load today own root posts for coverage",
            exc_info=True,
            extra={"character_id": ctx.character.id},
        )
        return []
    return [
        {
            "post_id": post.id,
            "coverage_text": " ".join(
                part
                for part in (
                    clip(post.title, 240),
                    clip(post.topic_signature, 500),
                    clip(post.novelty_basis, 500),
                    clip(post.body, 1200),
                )
                if part
            ),
        }
        for post in posts
    ]


def _today_root_writing_memory_for_prompt(
    ctx: LangGraphResidentContext, *, clip: ClipContextText
) -> list[dict[str, Any]]:
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return []
    start_utc, end_utc = _today_kst_window(ctx)
    items: list[dict[str, Any]] = []
    try:
        posts = list(
            db_scalars(
                select(Post)
                .where(Post.author_character_id == ctx.character.id)
                .where(Post.created_at >= start_utc)
                .where(Post.created_at <= end_utc)
                .where(Post.reply_to_post_id.is_(None))
                .where(Post.repost_of_post_id.is_(None))
                .where(Post.post_type == "post")
                .where(Post.deleted_at.is_(None))
                .where(Post.report_hidden_at.is_(None))
                .order_by(Post.created_at.desc(), Post.id.desc())
                .limit(12)
            )
        )
    except Exception:
        logger.debug(
            "Failed to load today root posts for writing memory",
            exc_info=True,
            extra={"character_id": ctx.character.id},
        )
        posts = []
    for post in posts:
        created_at = _aware_datetime(getattr(post, "created_at", None))
        items.append(
            {
                "kind": "root_post",
                "post_id": post.id,
                "created_at": created_at.isoformat() if created_at else None,
                "title": clip(post.title, 160),
                "summary": clip(post.novelty_basis or post.topic_signature, 300),
                "topic_signature": clip(post.topic_signature, 300),
                "topic_key": None,
                "source_post_id": None,
                "_sort_at": created_at or datetime.min.replace(tzinfo=UTC),
            }
        )
    items.sort(key=lambda item: item.get("_sort_at"), reverse=True)
    return [
        {key: value for key, value in item.items() if key != "_sort_at"}
        for item in items[:12]
    ]


def _recent_own_root_posts(
    ctx: LangGraphResidentContext, *, clip: ClipContextText
) -> list[dict[str, Any]]:
    posts = list(
        ctx.db.scalars(
            select(Post)
            .where(Post.author_character_id == ctx.character.id)
            .where(Post.reply_to_post_id.is_(None))
            .where(Post.repost_of_post_id.is_(None))
            .where(Post.post_type == "post")
            .where(Post.deleted_at.is_(None))
            .order_by(Post.created_at.desc(), Post.id.desc())
            .limit(8)
        )
    )
    return [
        {
            "post_id": post.id,
            "title": clip(post.title, 160),
            "topic_signature": clip(post.topic_signature, 240),
            "novelty_basis": clip(post.novelty_basis, 240),
            "created_at": post.created_at.isoformat(),
        }
        for post in posts
    ]


def _conversation_context_post(db: Session, post_id: str | None) -> Post | None:
    if not post_id:
        return None
    return db.scalar(
        select(Post)
        .where(
            Post.id == post_id,
            Post.deleted_at.is_(None),
            Post.report_hidden_at.is_(None),
        )
        .limit(1)
    )


def _character_handle_by_id(
    ctx: LangGraphResidentContext, character_id: str | None, *, clip: ClipContextText
) -> str | None:
    if not character_id:
        return None
    character = character_profile.get_character(ctx.db, character_id)
    if character is None:
        return None
    return clip(getattr(character, "handle", ""), 80) or None


def _character_for_handle(
    ctx: LangGraphResidentContext, handle: str | None
) -> Character | None:
    normalized = str(handle or "").strip().removeprefix("@").lower()
    if not normalized:
        return None
    return ctx.db.scalar(
        select(Character)
        .where(
            Character.handle == normalized,
            Character.deleted_at.is_(None),
            Character.moderation_status != "suspended",
        )
        .limit(1)
    )


def _relationship_source_post_available(
    ctx: LangGraphResidentContext, source_post_id: str | None
) -> Post | None:
    if not source_post_id:
        return None
    return ctx.db.scalar(
        select(Post)
        .where(
            Post.id == source_post_id,
            Post.deleted_at.is_(None),
            Post.report_hidden_at.is_(None),
            Post.visibility == "public",
        )
        .limit(1)
    )


def _character_already_replied_to_target(
    db: Session, *, character_id: str, post_id: str | None
) -> bool:
    if not post_id:
        return False
    existing_reply_id = db.scalar(
        select(Post.id)
        .where(
            Post.author_character_id == character_id,
            Post.reply_to_post_id == post_id,
            Post.post_type == "reply",
            Post.deleted_at.is_(None),
            Post.report_hidden_at.is_(None),
        )
        .limit(1)
    )
    return existing_reply_id is not None
