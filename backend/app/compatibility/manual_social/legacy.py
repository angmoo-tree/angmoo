"""Read-only compatibility facade for the pre-L4 manual-social boundary.

Canonical post and reply writes moved to :mod:`app.domains.social.public` in
L4 PR C. This module intentionally keeps only the owner feed/thread reads
until their remaining callers can move without widening the PR.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.domains.manual_social.api.schemas import (
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


def _post_read(db: Session, post: models.Post) -> ManualSocialPostRead:
    if post.world_id is None or post.author_world_character_id is None:
        raise ManualSocialConflictError("world_post_scope_missing")
    author = db.get(models.WorldCharacter, post.author_world_character_id)
    return ManualSocialPostRead(
        id=post.id,
        world_id=post.world_id,
        author_world_character_id=post.author_world_character_id,
        author_name=post.author_name,
        title=post.title,
        body=post.body,
        post_type=post.post_type,
        reply_to_post_id=post.reply_to_post_id,
        created_at=post.created_at,
        can_owner_reply=(
            post.reply_to_post_id is None
            and author is not None
            and author.status == "active"
            and author.control_mode == "autonomous"
            and author.activity_runtime_mode == "routine_resident_v1"
        ),
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
        items=[_post_read(db, post) for post in items],
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
    return ManualSocialFeedRead(
        world_id=world_id,
        owner_world_character_id=actor.id,
        items=[_post_read(db, root), *[_post_read(db, reply) for reply in replies]],
    )


__all__ = [
    "ManualSocialConflictError",
    "ManualSocialError",
    "ManualSocialForbiddenError",
    "ManualSocialNotFoundError",
    "get_owner_world_post_thread",
    "list_owner_world_feed",
]
