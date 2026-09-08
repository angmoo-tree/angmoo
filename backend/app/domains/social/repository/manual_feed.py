"""Exact World-scoped source, reply and like queries in the caller Session."""
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.models import feed as feed_models


def _visible(world_id: str):
    return (
        models.Post.world_id == world_id,
        models.Post.visibility == "public",
        models.Post.deleted_at.is_(None),
        models.Post.report_hidden_at.is_(None),
    )


def _descendants(world_id: str, post_ids: list[str]):
    # UNION (not UNION ALL) terminates malformed cycles; only visible edges
    # within this World are traversed. The root itself is excluded by readers.
    tree = select(models.Post.id.label("root_id"), models.Post.id.label("post_id")).where(
        models.Post.id.in_(post_ids), *_visible(world_id)
    ).cte("visible_descendants", recursive=True)
    return tree.union(select(tree.c.root_id, models.Post.id).join(
        tree, models.Post.reply_to_post_id == tree.c.post_id
    ).where(*_visible(world_id)))


def reply_counts(db: Session, *, world_id: str, post_ids: list[str]) -> dict[str, int]:
    tree = _descendants(world_id, post_ids)
    return {str(root): int(count) for root, count in db.execute(
        select(tree.c.root_id, func.count()).where(tree.c.post_id != tree.c.root_id)
        .group_by(tree.c.root_id)
    )}


def resolve_visible_root(db: Session, *, world_id: str, post_id: str) -> models.Post | None:
    ancestors = select(models.Post.id, models.Post.reply_to_post_id).where(
        models.Post.id == post_id, *_visible(world_id)
    ).cte("visible_ancestors", recursive=True)
    ancestors = ancestors.union(select(models.Post.id, models.Post.reply_to_post_id)
        .join(ancestors, models.Post.id == ancestors.c.reply_to_post_id)
        .where(*_visible(world_id)))
    root_id = select(ancestors.c.id).where(ancestors.c.reply_to_post_id.is_(None))
    return db.scalar(select(models.Post).where(models.Post.id.in_(root_id)))


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
    visible = select(models.Post.id).where(*_visible(world_id), models.Post.reply_to_post_id.is_(None)).cte(
        "visible_feed_posts", recursive=True
    )
    visible = visible.union(select(models.Post.id).join(
        visible, models.Post.reply_to_post_id == visible.c.id
    ).where(*_visible(world_id)))
    return list(
        db.scalars(
            select(models.Post)
            .join(visible, models.Post.id == visible.c.id)
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


def list_visible_replies(
    db: Session, *, world_id: str, root: models.Post, offset: int = 0,
    limit: int = 50, target_id: str | None = None,
) -> tuple[list[models.Post], int, int | None]:
    tree = _descendants(world_id, [root.id])
    query = select(models.Post).join(tree, models.Post.id == tree.c.post_id).where(
        models.Post.id != root.id
    )
    size = max(1, min(limit, 100))
    offset = max(0, offset)
    if target_id and target_id != root.id:
        # Jump directly to the target's page instead of treating later pages as
        # absent or accumulating an unbounded history in the browser.
        ranked = select(models.Post.id, func.row_number().over(
            order_by=(models.Post.created_at.asc(), models.Post.id.asc())
        ).label("position")).join(tree, models.Post.id == tree.c.post_id).where(
            models.Post.id != root.id
        ).subquery()
        position = db.scalar(select(ranked.c.position).where(ranked.c.id == target_id))
        if position is not None:
            offset = ((int(position) - 1) // size) * size
    rows = list(db.scalars(query.order_by(models.Post.created_at.asc(), models.Post.id.asc())
        .offset(offset).limit(size + 1)))
    return rows[:size], offset, offset + size if len(rows) > size else None

def blocked_authors(db: Session, *, world_id: str, viewer_id: str, author_ids: set[str]) -> set[str]:
    rows = db.execute(select(feed_models.WorldCharacterBlock.blocker_world_character_id,
        feed_models.WorldCharacterBlock.blocked_world_character_id).where(
            feed_models.WorldCharacterBlock.world_id == world_id,
            or_(
                (feed_models.WorldCharacterBlock.blocker_world_character_id == viewer_id)
                & feed_models.WorldCharacterBlock.blocked_world_character_id.in_(author_ids),
                (feed_models.WorldCharacterBlock.blocked_world_character_id == viewer_id)
                & feed_models.WorldCharacterBlock.blocker_world_character_id.in_(author_ids),
            ),
        ))
    return {second if first == viewer_id else first for first, second in rows}
