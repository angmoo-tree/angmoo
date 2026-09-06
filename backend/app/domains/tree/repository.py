from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from collections.abc import Callable
from sqlalchemy.sql.elements import ColumnElement

from app.domains.tree import models
from app.domains.tree.contracts import TreeAuthor


def list_tree_posts(
    db: Session,
    *,
    category: str,
    author_name_matches: Callable[[str], ColumnElement[bool]],
    limit: int,
    cursor: str | None = None,
    query: str | None = None,
) -> tuple[list[models.TreePost], str | None]:
    statement = (
        select(models.TreePost)
        .where(
            models.TreePost.hidden_at.is_(None),
            models.TreePost.category == category,
        )
        .options(
            selectinload(models.TreePost.author),
            selectinload(models.TreePost.related_character),
        )
    )
    normalized_query = (query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                models.TreePost.title.ilike(pattern),
                models.TreePost.body.ilike(pattern),
                author_name_matches(pattern),
                models.TreePost.comments.any(models.TreeComment.content.ilike(pattern)),
            )
        )
    if cursor:
        cursor_post = db.get(models.TreePost, cursor)
        if cursor_post is not None:
            statement = statement.where(
                or_(
                    models.TreePost.created_at < cursor_post.created_at,
                    and_(
                        models.TreePost.created_at == cursor_post.created_at,
                        models.TreePost.id > cursor_post.id,
                    ),
                )
            )
    posts = list(
        db.scalars(
            statement.order_by(
                models.TreePost.created_at.desc(), models.TreePost.id.asc()
            ).limit(limit)
        )
    )
    next_cursor = posts[-1].id if len(posts) == limit else None
    return posts, next_cursor


def get_tree_post(db: Session, post_id: str) -> models.TreePost | None:
    return db.scalar(
        select(models.TreePost)
        .where(models.TreePost.id == post_id, models.TreePost.hidden_at.is_(None))
        .options(
            selectinload(models.TreePost.author),
            selectinload(models.TreePost.related_character),
            selectinload(models.TreePost.comments).selectinload(
                models.TreeComment.author
            ),
        )
    )


def create_tree_post(
    db: Session,
    *,
    post_id: str,
    user: TreeAuthor,
    category: str,
    title: str,
    body: str,
    related_character_id: str | None,
) -> models.TreePost:
    post = models.TreePost(
        id=post_id,
        category=category,
        title=title.strip(),
        body=body.strip(),
        author_user_id=user.id,
        related_character_id=related_character_id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def create_tree_comment(
    db: Session, *, post: models.TreePost, user: TreeAuthor, content: str
) -> models.TreeComment:
    comment = models.TreeComment(
        post_id=post.id,
        author_user_id=user.id,
        content=content.strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def count_tree_comments(db: Session, post_id: str) -> int:
    return (
        db.scalar(
            select(func.count(models.TreeComment.id)).where(
                models.TreeComment.post_id == post_id,
                models.TreeComment.hidden_at.is_(None),
            )
        )
        or 0
    )
