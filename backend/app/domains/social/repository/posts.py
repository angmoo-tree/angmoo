"""Social-owned SQL; original caller transaction/flush/finish_write behavior is preserved."""

from datetime import date, datetime, timezone
import hashlib
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, aliased, selectinload
from app.domains.social.models import posts as models
from app.domains.social.schemas import community as schemas



def _visible_post_conditions():
    return (
        models.Post.deleted_at.is_(None),
        models.Post.report_hidden_at.is_(None),
    )

def _visible_reference_conditions():
    quoted_source = aliased(models.Post)
    reposted_source = aliased(models.Post)
    visible_quote_ids = select(quoted_source.id).where(
        quoted_source.deleted_at.is_(None),
        quoted_source.report_hidden_at.is_(None),
    )
    visible_repost_ids = select(reposted_source.id).where(
        reposted_source.deleted_at.is_(None),
        reposted_source.report_hidden_at.is_(None),
    )
    return (
        or_(
            models.Post.quote_post_id.is_(None),
            models.Post.quote_post_id.in_(visible_quote_ids),
        ),
        or_(
            models.Post.repost_of_post_id.is_(None),
            models.Post.repost_of_post_id.in_(visible_repost_ids),
        ),
    )

def is_report_hidden(post: models.Post) -> bool:
    return post.report_hidden_at is not None

def _like_search_terms(query: str) -> list[str]:
    raw = query.strip()
    if not raw:
        return []
    terms = [raw]
    if raw.startswith("@") and len(raw) > 1:
        terms.append(raw[1:])
    return list(dict.fromkeys(terms))

def _like_pattern(term: str) -> str:
    escaped = (
        term.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"

def character_has_authored_post(db: Session, character_id: str) -> bool:
    return (
        db.scalar(
            select(models.Post.id)
            .where(
                models.Post.author_character_id == character_id,
                models.Post.deleted_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )

def list_posts(db: Session) -> list[schemas.PostSummary]:
    comment_count = func.count(func.distinct(models.Comment.id)).label("comment_count")
    like_count = func.count(func.distinct(models.PostLike.id)).label("like_count")
    rows = db.execute(
        select(models.Post, comment_count, like_count)
        .outerjoin(models.Comment)
        .outerjoin(models.PostLike)
        .where(*_visible_post_conditions(), *_visible_reference_conditions())
        .group_by(models.Post.id)
        .order_by(models.Post.created_at.desc(), models.Post.id)
    ).all()

    return [
        schemas.PostSummary.model_validate(
            {
                "id": post.id,
                "author_name": post.author_name,
                "title": post.title,
                "body": post.body,
                "created_at": post.created_at,
                "post_type": post.post_type,
                "author_user_id": post.author_user_id,
                "author_character_id": post.author_character_id,
                "reply_to_post_id": post.reply_to_post_id,
                "quote_post_id": post.quote_post_id,
                "repost_of_post_id": post.repost_of_post_id,
                "comment_count": count,
                "like_count": likes,
                "reply_count": count_post_replies(db, post.id),
                "repost_count": count_post_reposts(db, post.id),
                "quote_count": count_post_quotes(db, post.id),
            }
        )
        for post, count, likes in rows
    ]

def get_post(db: Session, post_id: str) -> models.Post | None:
    return db.scalar(
        select(models.Post)
        .where(models.Post.id == post_id, *_visible_post_conditions())
        .options(selectinload(models.Post.comments))
    )

def get_post_including_report_hidden(db: Session, post_id: str) -> models.Post | None:
    return db.scalar(
        select(models.Post)
        .where(models.Post.id == post_id, models.Post.deleted_at.is_(None))
        .options(selectinload(models.Post.comments))
    )

def get_post_report(
    db: Session, *, post_id: str, reporter_user_id: str
) -> models.PostReport | None:
    return db.scalar(
        select(models.PostReport).where(
            models.PostReport.post_id == post_id,
            models.PostReport.reporter_user_id == reporter_user_id,
        )
    )

def count_post_reports(db: Session, post_id: str) -> int:
    return (
        db.scalar(
            select(func.count(models.PostReport.id)).where(
                models.PostReport.post_id == post_id
            )
        )
        or 0
    )

def list_timeline_posts(
    db: Session,
    *,
    limit: int,
    cursor: str | None = None,
    author_user_id: str | None = None,
    author_character_id: str | None = None,
    followed_user_ids: set[str] | None = None,
    followed_character_ids: set[str] | None = None,
    content_filter: str = "all",
) -> tuple[list[models.Post], str | None]:
    query = select(models.Post).where(
        *_visible_post_conditions(),
        *_visible_reference_conditions(),
        models.Post.reply_to_post_id.is_(None),
    )
    if author_user_id is not None:
        query = query.where(models.Post.author_user_id == author_user_id)
    if author_character_id is not None:
        query = query.where(models.Post.author_character_id == author_character_id)
    if content_filter == "posts":
        query = query.where(
            models.Post.post_type != "repost",
            models.Post.repost_of_post_id.is_(None),
        )
    elif content_filter == "reposts":
        query = query.where(
            models.Post.post_type == "repost",
            models.Post.repost_of_post_id.is_not(None),
        )
    if followed_user_ids is not None or followed_character_ids is not None:
        feed_filters = []
        if followed_user_ids:
            feed_filters.append(models.Post.author_user_id.in_(followed_user_ids))
        if followed_character_ids:
            feed_filters.append(
                models.Post.author_character_id.in_(followed_character_ids)
            )
        if not feed_filters:
            return [], None
        query = query.where(or_(*feed_filters))
    if cursor:
        cursor_post = db.get(models.Post, cursor)
        if cursor_post is not None:
            query = query.where(
                or_(
                    models.Post.created_at < cursor_post.created_at,
                    and_(
                        models.Post.created_at == cursor_post.created_at,
                        models.Post.id > cursor_post.id,
                    ),
                )
            )
    rows = list(
        db.scalars(
            query.order_by(models.Post.created_at.desc(), models.Post.id.asc()).limit(limit)
        )
    )
    next_cursor = rows[-1].id if len(rows) == limit else None
    return rows, next_cursor

def list_resident_scan_posts(
    db: Session,
    *,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[models.Post], str | None]:
    query = select(models.Post).where(
        *_visible_post_conditions(),
        *_visible_reference_conditions(),
        models.Post.reply_to_post_id.is_(None),
        models.Post.post_type != "repost",
        models.Post.repost_of_post_id.is_(None),
    )
    if cursor:
        cursor_post = db.get(models.Post, cursor)
        if cursor_post is not None:
            query = query.where(
                or_(
                    models.Post.created_at < cursor_post.created_at,
                    and_(
                        models.Post.created_at == cursor_post.created_at,
                        models.Post.id > cursor_post.id,
                    ),
                )
            )
    rows = list(
        db.scalars(
            query.order_by(models.Post.created_at.desc(), models.Post.id.asc()).limit(limit)
        )
    )
    next_cursor = rows[-1].id if len(rows) == limit else None
    return rows, next_cursor

def list_post_replies(db: Session, post_id: str, *, limit: int = 50) -> list[models.Post]:
    return list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.reply_to_post_id == post_id,
                *_visible_post_conditions(),
            )
            .order_by(models.Post.created_at.asc(), models.Post.id.asc())
            .limit(limit)
        )
    )

def list_post_thread_replies(
    db: Session, post_id: str, *, limit: int = 100
) -> list[models.Post]:
    seen = {post_id}
    replies: list[models.Post] = []
    frontier = [post_id]

    while frontier and len(replies) < limit:
        remaining = limit - len(replies)
        children = list(
            db.scalars(
                select(models.Post)
                .where(
                    models.Post.reply_to_post_id.in_(frontier),
                    *_visible_post_conditions(),
                )
                .order_by(models.Post.created_at.asc(), models.Post.id.asc())
                .limit(remaining)
            )
        )
        next_frontier = [child.id for child in children if child.id not in seen]
        if not next_frontier:
            break
        seen.update(next_frontier)
        replies.extend(child for child in children if child.id in next_frontier)
        frontier = next_frontier

    return replies

def count_post_comments(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.Comment.id)).where(models.Comment.post_id == post_id)
    ) or 0

def count_post_likes(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.PostLike.id)).where(models.PostLike.post_id == post_id)
    ) or 0

def count_post_replies(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.Post.id)).where(
            models.Post.reply_to_post_id == post_id,
            *_visible_post_conditions(),
        )
    ) or 0

def count_post_reposts(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.PostRepost.id)).where(models.PostRepost.post_id == post_id)
    ) or 0

def count_post_quotes(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.Post.id)).where(
            models.Post.quote_post_id == post_id,
            *_visible_post_conditions(),
        )
    ) or 0

def _lock_direct_user_like(db: Session, *, post_id: str, user_id: str) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    lock_key = int.from_bytes(
        hashlib.sha256(
            f"angmoo:direct-user-like:{post_id}:{user_id}:v1".encode("utf-8")
        ).digest()[:8],
        byteorder="big",
        signed=True,
    )
    db.execute(
        text("select pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )

def delete_repost_event_for_timeline_post(db: Session, *, post: models.Post) -> bool:
    if post.post_type != "repost" or post.repost_of_post_id is None:
        return False
    query = select(models.PostRepost).where(
        models.PostRepost.post_id == post.repost_of_post_id
    )
    if post.author_character_id is not None:
        query = query.where(models.PostRepost.character_id == post.author_character_id)
    elif post.author_user_id is not None:
        query = query.where(
            models.PostRepost.user_id == post.author_user_id,
            models.PostRepost.character_id.is_(None),
        )
    else:
        return False
    repost = db.scalar(query)
    if repost is None:
        return False
    db.delete(repost)
    db.commit()
    return True

def delete_repost_events_for_post(db: Session, *, post: models.Post) -> int:
    rows = list(
        db.scalars(
            select(models.PostRepost).where(models.PostRepost.post_id == post.id)
        )
    )
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()
    return len(rows)

def soft_delete_timeline_reposts_for_source(
    db: Session, *, post: models.Post, deleted_at: datetime
) -> list[models.Post]:
    rows = list(
        db.scalars(
            select(models.Post).where(
                models.Post.deleted_at.is_(None),
                models.Post.post_type == "repost",
                models.Post.repost_of_post_id == post.id,
            )
        )
    )
    for row in rows:
        row.deleted_at = deleted_at
    if rows:
        db.commit()
    return rows

def soft_delete_post_tree(
    db: Session, *, post: models.Post, deleted_at: datetime
) -> list[models.Post]:
    seen = {post.id}
    frontier = [post.id]
    rows = [post] if post.deleted_at is None else []

    while frontier:
        children = list(
            db.scalars(
                select(models.Post).where(models.Post.reply_to_post_id.in_(frontier))
            )
        )
        next_frontier: list[str] = []
        for child in children:
            if child.id in seen:
                continue
            seen.add(child.id)
            next_frontier.append(child.id)
            if child.deleted_at is None:
                rows.append(child)
        frontier = next_frontier

    for row in rows:
        row.deleted_at = deleted_at
    if rows:
        db.commit()
    return rows
