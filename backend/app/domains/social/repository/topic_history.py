"""Social root-post history and nullable topic record reads."""

from __future__ import annotations
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models


def recent_own_root_posts(
    db: Session, *, character_id: str, cutoff: datetime, limit: int
) -> list[models.Post]:
    posts = list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.author_character_id == character_id,
                models.Post.reply_to_post_id.is_(None),
                models.Post.post_type != "repost",
                models.Post.repost_of_post_id.is_(None),
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                models.Post.created_at >= cutoff,
            )
            .order_by(models.Post.created_at.desc(), models.Post.id.desc())
            .limit(limit)
        )
    )
    return posts


def get_topic_post(db: Session, post_id: str) -> models.Post | None:
    return db.get(models.Post, post_id)
