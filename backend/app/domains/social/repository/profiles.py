from app.core import unit_of_work
from app.domains.social.contracts.actors import SocialUser, SocialCharacter
"""Social-owned SQL; original caller transaction/flush/finish_write behavior is preserved."""

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, aliased, selectinload
from app.domains.social.models import posts as models
from app.domains.social.utils.cursors import _parse_int_cursor
from app.domains.social.repository.posts import _visible_post_conditions
from app.domains.social.repository.posts import _visible_reference_conditions



def list_profile_posts(
    db: Session,
    *,
    limit: int,
    cursor: str | None = None,
    author_user_id: str | None = None,
    author_character_id: str | None = None,
    replies: bool = False,
) -> tuple[list[models.Post], str | None]:
    query = select(models.Post).where(
        *_visible_post_conditions(), *_visible_reference_conditions()
    )
    if replies:
        query = query.where(models.Post.reply_to_post_id.is_not(None))
    else:
        query = query.where(models.Post.reply_to_post_id.is_(None))
    if author_user_id is not None:
        query = query.where(models.Post.author_user_id == author_user_id)
    if author_character_id is not None:
        query = query.where(models.Post.author_character_id == author_character_id)
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

def list_liked_profile_posts(
    db: Session,
    *,
    limit: int,
    cursor: str | None = None,
    user_id: str | None = None,
    character_id: str | None = None,
) -> tuple[list[models.Post], str | None]:
    query = (
        select(models.Post, models.PostLike.created_at)
        .join(models.PostLike, models.PostLike.post_id == models.Post.id)
        .where(*_visible_post_conditions(), *_visible_reference_conditions())
    )
    cursor_like_query = select(models.PostLike.created_at).where(
        models.PostLike.post_id == cursor
    )
    if character_id is not None:
        query = query.where(models.PostLike.character_id == character_id)
        cursor_like_query = cursor_like_query.where(
            models.PostLike.character_id == character_id
        )
    elif user_id is not None:
        query = query.where(
            models.PostLike.user_id == user_id,
            models.PostLike.character_id.is_(None),
        )
        cursor_like_query = cursor_like_query.where(
            models.PostLike.user_id == user_id,
            models.PostLike.character_id.is_(None),
        )
    if cursor:
        cursor_created_at = db.scalar(cursor_like_query)
        if cursor_created_at is not None:
            query = query.where(
                or_(
                    models.PostLike.created_at < cursor_created_at,
                    and_(
                        models.PostLike.created_at == cursor_created_at,
                        models.Post.id > cursor,
                    ),
                )
            )
    rows = db.execute(
        query.order_by(models.PostLike.created_at.desc(), models.Post.id.asc()).limit(limit)
    ).all()
    posts = [post for post, _created_at in rows]
    next_cursor = posts[-1].id if len(posts) == limit else None
    return posts, next_cursor

def get_followed_profiles_for_user(db: Session, user_id: str) -> tuple[set[str], set[str]]:
    rows = db.scalars(
        select(models.ProfileFollow).where(models.ProfileFollow.follower_user_id == user_id)
    )
    followed_user_ids: set[str] = set()
    followed_character_ids: set[str] = set()
    for row in rows:
        if row.target_user_id:
            followed_user_ids.add(row.target_user_id)
        if row.target_character_id:
            followed_character_ids.add(row.target_character_id)
    return followed_user_ids, followed_character_ids

def get_followed_profiles_for_character(
    db: Session, character_id: str
) -> tuple[set[str], set[str]]:
    rows = db.scalars(
        select(models.ProfileFollow).where(
            models.ProfileFollow.follower_character_id == character_id
        )
    )
    followed_user_ids: set[str] = set()
    followed_character_ids: set[str] = set()
    for row in rows:
        if row.target_user_id:
            followed_user_ids.add(row.target_user_id)
        if row.target_character_id:
            followed_character_ids.add(row.target_character_id)
    return followed_user_ids, followed_character_ids

def count_profile_followers(
    db: Session,
    *,
    user_id: str | None = None,
    character_id: str | None = None,
    follower_type: str | None = None,
) -> int:
    query = select(func.count(models.ProfileFollow.id))
    if user_id is not None:
        query = query.where(models.ProfileFollow.target_user_id == user_id)
    else:
        query = query.where(models.ProfileFollow.target_character_id == character_id)
    if follower_type == "user":
        query = query.where(models.ProfileFollow.follower_user_id.is_not(None))
    if follower_type == "character":
        query = query.where(models.ProfileFollow.follower_character_id.is_not(None))
    return db.scalar(query) or 0

def count_profile_following(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = select(func.count(models.ProfileFollow.id))
    if user_id is not None:
        query = query.where(models.ProfileFollow.follower_user_id == user_id)
    else:
        query = query.where(models.ProfileFollow.follower_character_id == character_id)
    return db.scalar(query) or 0

def list_profile_following(
    db: Session,
    *,
    user_id: str | None = None,
    character_id: str | None = None,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[models.ProfileFollow], str | None]:
    query = select(models.ProfileFollow)
    if user_id is not None:
        query = query.where(models.ProfileFollow.follower_user_id == user_id)
    else:
        query = query.where(models.ProfileFollow.follower_character_id == character_id)
    if cursor:
        cursor_id = _parse_int_cursor(cursor)
        if cursor_id is not None:
            query = query.where(models.ProfileFollow.id < cursor_id)
    rows = list(
        db.scalars(query.order_by(models.ProfileFollow.id.desc()).limit(limit + 1))
    )
    return rows[:limit], str(rows[limit - 1].id) if len(rows) > limit else None

def list_profile_followers(
    db: Session,
    *,
    user_id: str | None = None,
    character_id: str | None = None,
    follower_type: str | None = None,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[models.ProfileFollow], str | None]:
    query = select(models.ProfileFollow)
    if user_id is not None:
        query = query.where(models.ProfileFollow.target_user_id == user_id)
    else:
        query = query.where(models.ProfileFollow.target_character_id == character_id)
    if follower_type == "user":
        query = query.where(models.ProfileFollow.follower_user_id.is_not(None))
    if follower_type == "character":
        query = query.where(models.ProfileFollow.follower_character_id.is_not(None))
    if cursor:
        cursor_id = _parse_int_cursor(cursor)
        if cursor_id is not None:
            query = query.where(models.ProfileFollow.id < cursor_id)
    rows = list(
        db.scalars(query.order_by(models.ProfileFollow.id.desc()).limit(limit + 1))
    )
    return rows[:limit], str(rows[limit - 1].id) if len(rows) > limit else None

def count_profile_posts(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = select(func.count(models.Post.id)).where(
        *_visible_post_conditions(),
        *_visible_reference_conditions(),
        models.Post.reply_to_post_id.is_(None),
    )
    if user_id is not None:
        query = query.where(models.Post.author_user_id == user_id)
    else:
        query = query.where(models.Post.author_character_id == character_id)
    return db.scalar(query) or 0

def count_profile_replies(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = select(func.count(models.Post.id)).where(
        *_visible_post_conditions(),
        *_visible_reference_conditions(),
        models.Post.reply_to_post_id.is_not(None),
    )
    if user_id is not None:
        query = query.where(models.Post.author_user_id == user_id)
    else:
        query = query.where(models.Post.author_character_id == character_id)
    return db.scalar(query) or 0

def count_profile_received_likes(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = (
        select(func.count(models.PostLike.id))
        .join(models.Post, models.PostLike.post_id == models.Post.id)
        .where(*_visible_post_conditions(), *_visible_reference_conditions())
    )
    if user_id is not None:
        query = query.where(models.Post.author_user_id == user_id)
    else:
        query = query.where(models.Post.author_character_id == character_id)
    return db.scalar(query) or 0

def count_profile_likes(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = (
        select(func.count(models.PostLike.id))
        .join(models.Post, models.PostLike.post_id == models.Post.id)
        .where(*_visible_post_conditions(), *_visible_reference_conditions())
    )
    if character_id is not None:
        query = query.where(models.PostLike.character_id == character_id)
    else:
        query = query.where(
            models.PostLike.user_id == user_id,
            models.PostLike.character_id.is_(None),
        )
    return db.scalar(query) or 0


def create_follow(
    db: Session,
    *,
    follower_user: SocialUser | None,
    follower_character: SocialCharacter | None,
    target_user: SocialUser | None,
    target_character: SocialCharacter | None,
) -> tuple[models.ProfileFollow, bool]:
    query = select(models.ProfileFollow).where(
        models.ProfileFollow.follower_user_id
        == (follower_user.id if follower_user else None),
        models.ProfileFollow.follower_character_id
        == (follower_character.id if follower_character else None),
        models.ProfileFollow.target_user_id == (target_user.id if target_user else None),
        models.ProfileFollow.target_character_id
        == (target_character.id if target_character else None),
    )
    existing = db.scalar(query)
    if existing is not None:
        return existing, False
    follow = models.ProfileFollow(
        follower_user_id=follower_user.id if follower_user else None,
        follower_character_id=follower_character.id if follower_character else None,
        target_user_id=target_user.id if target_user else None,
        target_character_id=target_character.id if target_character else None,
    )
    db.add(follow)
    unit_of_work.finish_write(db, follow)
    return follow, True


def profile_follow_exists(
    db: Session,
    *,
    follower_user: SocialUser | None,
    follower_character: SocialCharacter | None,
    target_user: SocialUser | None,
    target_character: SocialCharacter | None,
) -> bool:
    return (
        db.scalar(
            select(models.ProfileFollow.id).where(
                models.ProfileFollow.follower_user_id
                == (follower_user.id if follower_user else None),
                models.ProfileFollow.follower_character_id
                == (follower_character.id if follower_character else None),
                models.ProfileFollow.target_user_id == (target_user.id if target_user else None),
                models.ProfileFollow.target_character_id
                == (target_character.id if target_character else None),
            )
        )
        is not None
    )


def delete_follow(
    db: Session,
    *,
    follower_user: SocialUser | None,
    follower_character: SocialCharacter | None,
    target_user: SocialUser | None,
    target_character: SocialCharacter | None,
) -> bool:
    follow = db.scalar(
        select(models.ProfileFollow).where(
            models.ProfileFollow.follower_user_id
            == (follower_user.id if follower_user else None),
            models.ProfileFollow.follower_character_id
            == (follower_character.id if follower_character else None),
            models.ProfileFollow.target_user_id == (target_user.id if target_user else None),
            models.ProfileFollow.target_character_id
            == (target_character.id if target_character else None),
        )
    )
    if follow is None:
        return False
    db.delete(follow)
    unit_of_work.finish_write(db)
    return True
