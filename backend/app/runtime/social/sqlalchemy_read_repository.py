"""Runtime SQLAlchemy owner feed and thread reads for social activity."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.domains.social.api.schemas import (
    ManualSocialFeedRead,
    ManualSocialPostRead,
)
from app.domains.social.domain import (
    SocialWriteConflictError as ManualSocialConflictError,
)
from app.domains.social.domain import (
    SocialWriteError as ManualSocialError,
)
from app.domains.social.domain import (
    SocialWriteForbiddenError as ManualSocialForbiddenError,
)
from app.domains.social.domain import (
    SocialWriteNotFoundError as ManualSocialNotFoundError,
)
from app.domains.world_characters.public import (
    SqlAlchemyOwnerControlledIdentityRepository,
)
from app.runtime.relationships.sqlalchemy_social_event import (
    world_character_pair_is_blocked,
)


class _SocialPersistenceModels:
    """L6-removable ORM mapping exposed only to sibling social adapters."""

    Character = models.Character
    Post = models.Post
    PostLike = models.PostLike
    PostMedia = models.PostMedia
    WorldCharacter = models.WorldCharacter
    WorldCharacterBlock = models.WorldCharacterBlock
    WorldCharacterFeedObservation = models.WorldCharacterFeedObservation
    WorldMembership = models.WorldMembership


social_persistence_models = _SocialPersistenceModels()


def _owner_actor(
    db: Session, *, world_id: str, current_user_id: str
) -> tuple[models.WorldCharacter, models.Character]:
    snapshot = SqlAlchemyOwnerControlledIdentityRepository(db).get(
        world_id=world_id,
        current_user_id=current_user_id,
    )
    world_character = db.get(models.WorldCharacter, snapshot.world_character_id)
    character = db.get(models.Character, snapshot.character_id)
    if (
        world_character is None
        or character is None
        or character.deleted_at is not None
        or character.owner_id != current_user_id
        or world_character.world_id != world_id
        or world_character.owner_user_id != current_user_id
        or world_character.control_mode != "owner_controlled"
        or world_character.status != "active"
        or world_character.autonomous_enabled
    ):
        raise ManualSocialForbiddenError("owner_actor_invalid")
    membership = db.get(models.WorldMembership, world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_id
        or membership.user_id != current_user_id
        or membership.status != "active"
    ):
        raise ManualSocialForbiddenError("owner_membership_inactive")
    return world_character, character


def _post_read(
    db: Session,
    post: models.Post,
    *,
    reply_count: int,
    like_count: int,
    viewer_world_character_id: str,
) -> ManualSocialPostRead:
    if post.world_id is None or post.author_world_character_id is None:
        raise ManualSocialConflictError("world_post_scope_missing")
    author = db.get(models.WorldCharacter, post.author_world_character_id)
    author_character = (
        db.get(models.Character, author.character_id) if author is not None else None
    )
    local_profile = author.local_profile if author is not None else None
    local_profile = local_profile if isinstance(local_profile, dict) else {}
    author_profile_available = _author_profile_available(
        db,
        world_id=post.world_id,
        author_world_character_id=post.author_world_character_id,
        viewer_world_character_id=viewer_world_character_id,
    )
    return ManualSocialPostRead(
        id=post.id,
        world_id=post.world_id,
        author_world_character_id=post.author_world_character_id,
        author_name=post.author_name,
        author_handle=author_character.handle if author_character is not None else None,
        author_avatar_url=(
            str(local_profile.get("avatar_url") or author_character.avatar_url)
            if author_character is not None
            and (local_profile.get("avatar_url") or author_character.avatar_url)
            else None
        ),
        title=post.title,
        body=post.body,
        post_type=post.post_type,
        reply_to_post_id=post.reply_to_post_id,
        created_at=post.created_at,
        reply_count=reply_count,
        like_count=like_count,
        author_profile_capability=(
            "available" if author_profile_available else "unavailable"
        ),
        can_owner_reply=(
            post.reply_to_post_id is None
            and author is not None
            and author.status == "active"
            and author.control_mode == "autonomous"
            and author.activity_runtime_mode == "routine_resident_v1"
        ),
    )


def _post_reads(
    db: Session,
    *,
    world_id: str,
    posts: list[models.Post],
    viewer_world_character_id: str,
) -> list[ManualSocialPostRead]:
    post_ids = [post.id for post in posts]
    if not post_ids:
        return []

    reply_counts = {
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
    like_counts = {
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
    return [
        _post_read(
            db,
            post,
            reply_count=reply_counts.get(post.id, 0),
            like_count=like_counts.get(post.id, 0),
            viewer_world_character_id=viewer_world_character_id,
        )
        for post in posts
    ]


def _author_profile_available(
    db: Session,
    *,
    world_id: str,
    author_world_character_id: str,
    viewer_world_character_id: str,
) -> bool:
    active_author_id = db.scalar(
        select(models.WorldCharacter.id)
        .join(
            models.Character,
            models.Character.id == models.WorldCharacter.character_id,
        )
        .join(
            models.WorldMembership,
            (models.WorldMembership.id == models.WorldCharacter.membership_id)
            & (models.WorldMembership.world_id == models.WorldCharacter.world_id),
        )
        .where(
            models.WorldCharacter.id == author_world_character_id,
            models.WorldCharacter.world_id == world_id,
            models.WorldCharacter.status == "active",
            models.WorldMembership.status == "active",
            models.Character.deleted_at.is_(None),
            models.Character.moderation_status == "active",
        )
    )
    if active_author_id is None:
        return False
    if author_world_character_id == viewer_world_character_id:
        return True
    return not world_character_pair_is_blocked(
        db,
        world_id=world_id,
        first_world_character_id=viewer_world_character_id,
        second_world_character_id=author_world_character_id,
    )


def list_owner_world_feed(
    db: Session, *, world_id: str, current_user_id: str, limit: int = 100
) -> ManualSocialFeedRead:
    actor, _character = _owner_actor(
        db, world_id=world_id, current_user_id=current_user_id
    )
    items = list(
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
    return ManualSocialFeedRead(
        world_id=world_id,
        owner_world_character_id=actor.id,
        items=_post_reads(
            db,
            world_id=world_id,
            posts=items,
            viewer_world_character_id=actor.id,
        ),
    )


def get_owner_world_post_thread(
    db: Session,
    *,
    world_id: str,
    post_id: str,
    current_user_id: str,
) -> ManualSocialFeedRead:
    """Read one root post and visible replies inside an exact World scope."""

    actor, _character = _owner_actor(
        db, world_id=world_id, current_user_id=current_user_id
    )
    root = db.get(models.Post, post_id)
    if (
        root is None
        or root.world_id != world_id
        or root.reply_to_post_id is not None
        or root.visibility != "public"
        or root.deleted_at is not None
        or root.report_hidden_at is not None
    ):
        raise ManualSocialNotFoundError("post_not_in_world")
    replies = list(
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
    items = [root, *replies]
    return ManualSocialFeedRead(
        world_id=world_id,
        owner_world_character_id=actor.id,
        items=_post_reads(
            db,
            world_id=world_id,
            posts=items,
            viewer_world_character_id=actor.id,
        ),
    )


__all__ = [
    "ManualSocialConflictError",
    "ManualSocialError",
    "ManualSocialForbiddenError",
    "ManualSocialNotFoundError",
    "get_owner_world_post_thread",
    "list_owner_world_feed",
    "social_persistence_models",
]
