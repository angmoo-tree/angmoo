"""Exact World-scoped source, reply and like queries in the caller Session."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models


def reply_counts(db: Session, *, world_id: str, post_ids: list[str]) -> dict[str, int]:
    return {
        str(parent_id): int(count)
        for parent_id, count in db.execute(
            select(
                models.Post.reply_to_post_id,
                func.count(models.Post.id),
            )
            .where(
                models.Post.world_id == world_id,
                models.Post.reply_to_post_id.in_(post_ids),
                models.Post.visibility == "public",
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
            )
            .group_by(models.Post.reply_to_post_id)
        ).all()
        if parent_id is not None
    }


def like_counts(db: Session, *, post_ids: list[str]) -> dict[str, int]:
    return {
        str(post_id): int(count)
        for post_id, count in db.execute(
            select(
                models.PostLike.post_id,
                func.count(models.PostLike.id),
            )
            .where(models.PostLike.post_id.in_(post_ids))
            .group_by(models.PostLike.post_id)
        ).all()
    }


def list_visible_posts(db: Session, *, world_id: str, limit: int) -> list[models.Post]:
    return list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.world_id == world_id,
                models.Post.visibility == "public",
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
            )
            .order_by(models.Post.created_at.desc(), models.Post.id.desc())
            .limit(max(1, min(limit, 200)))
        )
    )


def list_visible_replies(db: Session, *, world_id: str, root: models.Post) -> list[models.Post]:
    return list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.world_id == world_id,
                models.Post.reply_to_post_id == root.id,
                models.Post.visibility == "public",
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
            )
            .order_by(models.Post.created_at.asc(), models.Post.id.asc())
        )
    )
