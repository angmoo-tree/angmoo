"""Reaction presence and visible reply traversal in the caller Session."""

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models


def _character_already_liked_post(
    db: Session, *, character_id: str, post_id: str
) -> bool:
    return (
        db.scalar(
            select(models.PostLike.id)
            .where(
                models.PostLike.post_id == post_id,
                models.PostLike.character_id == character_id,
            )
            .limit(1)
        )
        is not None
    )


def _character_already_reposted_post(
    db: Session, *, character_id: str, post_id: str
) -> bool:
    return (
        db.scalar(
            select(models.PostRepost.id)
            .where(
                models.PostRepost.post_id == post_id,
                models.PostRepost.character_id == character_id,
            )
            .limit(1)
        )
        is not None
    )


def _thread_reply_post_ids(db: Session, root_post_id: str) -> list[str]:
    seen = {root_post_id}
    reply_ids: list[str] = []
    frontier = [root_post_id]
    while frontier:
        children = list(
            db.scalars(
                select(models.Post.id).where(
                    models.Post.reply_to_post_id.in_(frontier),
                    models.Post.deleted_at.is_(None),
                    models.Post.report_hidden_at.is_(None),
                )
            )
        )
        next_frontier = [post_id for post_id in children if post_id not in seen]
        if not next_frontier:
            break
        seen.update(next_frontier)
        reply_ids.extend(next_frontier)
        frontier = next_frontier
    return reply_ids
