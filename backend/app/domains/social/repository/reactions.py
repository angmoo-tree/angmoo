"""Persist reactions and deduplicate in the caller's existing write boundary."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core import unit_of_work
from app.domains.social.models import posts as models
from app.domains.social.schemas import community as schemas
from app.domains.social.contracts.actors import SocialUser, SocialCharacter
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from app.domains.social.repository.posts import get_post_report, _lock_direct_user_like


def create_post_report(
    db: Session,
    *,
    post: models.Post,
    reporter_user: SocialUser,
    data: schemas.PostReportCreate,
) -> tuple[models.PostReport, bool]:
    existing = get_post_report(db, post_id=post.id, reporter_user_id=reporter_user.id)
    if existing is not None:
        return existing, False
    report = models.PostReport(
        post_id=post.id,
        reporter_user_id=reporter_user.id,
        reason=data.reason,
        details=(data.details.strip() or None) if data.details else None,
    )
    db.add(report)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = get_post_report(
            db, post_id=post.id, reporter_user_id=reporter_user.id
        )
        if existing is not None:
            return existing, False
        raise
    db.refresh(report)
    return report, True


def like_post(
    db: Session,
    *,
    post: models.Post,
    user: SocialUser,
    character: SocialCharacter | None,
) -> tuple[models.PostLike, bool]:
    if character is None:
        _lock_direct_user_like(db, post_id=post.id, user_id=user.id)
    query = select(models.PostLike).where(models.PostLike.post_id == post.id)
    if character is None:
        query = query.where(
            models.PostLike.user_id == user.id,
            models.PostLike.character_id.is_(None),
        )
    else:
        query = query.where(models.PostLike.character_id == character.id)
    existing = db.scalar(query)
    if existing is not None:
        return existing, False
    like = models.PostLike(
        post_id=post.id,
        user_id=user.id,
        character_id=character.id if character else None,
    )
    db.add(like)
    try:
        unit_of_work.finish_write(db, like)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(query)
        if existing is not None:
            return existing, False
        raise
    return like, True


def unlike_post(
    db: Session,
    *,
    post: models.Post,
    user: SocialUser,
    character: SocialCharacter | None,
) -> bool:
    query = select(models.PostLike).where(models.PostLike.post_id == post.id)
    if character is None:
        query = query.where(
            models.PostLike.user_id == user.id,
            models.PostLike.character_id.is_(None),
        )
    else:
        query = query.where(models.PostLike.character_id == character.id)
    like = db.scalar(query)
    if like is None:
        return False
    db.delete(like)
    unit_of_work.finish_write(db)
    return True


def create_repost(
    db: Session,
    *,
    post: models.Post,
    user: SocialUser,
    character: SocialCharacter | None,
) -> tuple[models.PostRepost, bool]:
    query = select(models.PostRepost).where(models.PostRepost.post_id == post.id)
    if character is None:
        query = query.where(
            models.PostRepost.user_id == user.id,
            models.PostRepost.character_id.is_(None),
        )
    else:
        query = query.where(models.PostRepost.character_id == character.id)
    existing = db.scalar(query)
    if existing is not None:
        return existing, False
    repost = models.PostRepost(
        post_id=post.id,
        user_id=user.id if character is None else None,
        character_id=character.id if character else None,
    )
    db.add(repost)
    unit_of_work.finish_write(db, repost)
    return repost, True


def get_timeline_repost(
    db: Session,
    *,
    post: models.Post,
    user: SocialUser,
    character: SocialCharacter | None,
) -> models.Post | None:
    query = select(models.Post).where(
        models.Post.deleted_at.is_(None),
        models.Post.report_hidden_at.is_(None),
        models.Post.post_type == "repost",
        models.Post.repost_of_post_id == post.id,
    )
    if character is None:
        query = query.where(
            models.Post.author_user_id == user.id,
            models.Post.author_character_id.is_(None),
        )
    else:
        query = query.where(models.Post.author_character_id == character.id)
    return db.scalar(query.order_by(models.Post.created_at.desc(), models.Post.id.asc()).limit(1))


def delete_repost(
    db: Session,
    *,
    post: models.Post,
    user: SocialUser,
    character: SocialCharacter | None,
) -> bool:
    query = select(models.PostRepost).where(models.PostRepost.post_id == post.id)
    if character is None:
        query = query.where(
            models.PostRepost.user_id == user.id,
            models.PostRepost.character_id.is_(None),
        )
    else:
        query = query.where(models.PostRepost.character_id == character.id)
    repost = db.scalar(query)
    if repost is None:
        return False
    db.delete(repost)
    unit_of_work.finish_write(db)
    return True


def delete_timeline_reposts(
    db: Session,
    *,
    post: models.Post,
    user: SocialUser,
    character: SocialCharacter | None,
) -> int:
    query = select(models.Post).where(
        models.Post.deleted_at.is_(None),
        models.Post.post_type == "repost",
        models.Post.repost_of_post_id == post.id,
    )
    if character is None:
        query = query.where(
            models.Post.author_user_id == user.id,
            models.Post.author_character_id.is_(None),
        )
    else:
        query = query.where(models.Post.author_character_id == character.id)
    rows = list(db.scalars(query))
    now = datetime.now(timezone.utc)
    for row in rows:
        row.deleted_at = now
    if rows:
        unit_of_work.finish_write(db)
    return len(rows)
