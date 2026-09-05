"""Original Social relationship and visible-thread reads for resident decisions."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.social.models import posts as models
from app.domains.social.repository import posts as community_crud


def _has_character_like(db: Session, *, post_id: str, character_id: str) -> bool:
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


def _has_character_repost(db: Session, *, post_id: str, character_id: str) -> bool:
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


def _thread_reply_post_ids_for_action_gate(db: Session, root_post_id: str) -> list[str]:
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


def _has_character_replied_to_thread(
    db: Session, *, root_post_id: str, character_id: str
) -> bool:
    reply_ids = _thread_reply_post_ids_for_action_gate(db, root_post_id)
    if not reply_ids:
        return False
    return (
        db.scalar(
            select(models.Post.id)
            .where(
                models.Post.id.in_(reply_ids),
                models.Post.author_character_id == character_id,
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def _is_direct_reply_to_character_post_for_action_gate(
    db: Session, *, post_id: str, character_id: str
) -> bool:
    post = community_crud.get_post(db, post_id)
    if post is None or post.reply_to_post_id is None:
        return False
    parent = community_crud.get_post(db, post.reply_to_post_id)
    return parent is not None and parent.author_character_id == character_id


def find_follow_id(
    db: Session, *, follower_character_id: str, target_character_id: str
) -> int | None:
    return db.scalar(
            select(models.ProfileFollow.id)
            .where(
                models.ProfileFollow.follower_character_id == follower_character_id,
                models.ProfileFollow.target_character_id == target_character_id,
            )
            .limit(1)
        )
