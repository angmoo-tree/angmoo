"""Owner feed/thread visibility, profile capability and response composition."""
from __future__ import annotations
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.schemas.manual import ManualSocialFeedRead, ManualSocialPostRead
from app.domains.social.contracts.actors import SocialCharacter
from app.domains.social.contracts.manual_feed import ManualFeedReferences, ManualFeedWorldCharacter
from app.domains.social.contracts.writes import SocialWriteConflictError as ManualSocialConflictError, SocialWriteForbiddenError as ManualSocialForbiddenError, SocialWriteNotFoundError as ManualSocialNotFoundError
from app.domains.social.repository import manual_feed as queries, event_evidence as post_queries


def _owner_actor(
    references: ManualFeedReferences, *, world_id: str, current_user_id: str
) -> tuple[ManualFeedWorldCharacter, SocialCharacter]:
    snapshot = references.get_owner_identity(
        world_id=world_id,
        current_user_id=current_user_id,
    )
    world_character = references.get_world_character(snapshot.world_character_id)
    character = references.get_character(snapshot.character_id)
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
    membership = references.get_membership(world_character.membership_id)
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
    references: ManualFeedReferences,
    reply_count: int,
    like_count: int,
    viewer_world_character_id: str,
    blocked_author_ids: set[str],
) -> ManualSocialPostRead:
    if post.world_id is None or post.author_world_character_id is None:
        raise ManualSocialConflictError("world_post_scope_missing")
    author = references.get_world_character(post.author_world_character_id)
    author_character = (
        references.get_character(author.character_id) if author is not None else None
    )
    local_profile = author.local_profile if author is not None else None
    local_profile = local_profile if isinstance(local_profile, dict) else {}
    author_profile_available = _author_profile_available(
        db,
        references=references,
        world_id=post.world_id,
        author_world_character_id=post.author_world_character_id,
        viewer_world_character_id=viewer_world_character_id,
        blocked_author_ids=blocked_author_ids,
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
    references: ManualFeedReferences,
    world_id: str,
    posts: list[models.Post],
    viewer_world_character_id: str,
) -> list[ManualSocialPostRead]:
    post_ids = [post.id for post in posts]
    if not post_ids:
        return []

    author_ids = {post.author_world_character_id for post in posts if post.author_world_character_id}
    references.prepare_authors(world_id=world_id, author_ids=author_ids)
    blocked = queries.blocked_authors(db, world_id=world_id, viewer_id=viewer_world_character_id, author_ids=author_ids)

    reply_counts = queries.reply_counts(db, world_id=world_id, post_ids=post_ids)
    like_counts = queries.like_counts(db, post_ids=post_ids)
    return [
        _post_read(
            db,
            post,
            references=references,
            reply_count=reply_counts.get(post.id, 0),
            like_count=like_counts.get(post.id, 0),
            viewer_world_character_id=viewer_world_character_id,
            blocked_author_ids=blocked,
        )
        for post in posts
    ]


def _author_profile_available(
    db: Session,
    *,
    references: ManualFeedReferences,
    world_id: str,
    author_world_character_id: str,
    viewer_world_character_id: str,
    blocked_author_ids: set[str],
) -> bool:
    active_author_id = references.active_author_id(world_id=world_id, author_world_character_id=author_world_character_id)
    if active_author_id is None:
        return False
    if author_world_character_id == viewer_world_character_id:
        return True
    return author_world_character_id not in blocked_author_ids


def list_owner_world_feed(
    db: Session, *, references: ManualFeedReferences, world_id: str, current_user_id: str, limit: int = 100
) -> ManualSocialFeedRead:
    actor, _character = _owner_actor(
        references, world_id=world_id, current_user_id=current_user_id
    )
    items = queries.list_visible_posts(db, world_id=world_id, limit=limit)
    return ManualSocialFeedRead(
        world_id=world_id,
        owner_world_character_id=actor.id,
        items=_post_reads(
            db,
            references=references,
            world_id=world_id,
            posts=items,
            viewer_world_character_id=actor.id,
        ),
    )


def get_owner_world_post_thread(
    db: Session,
    *,
    references: ManualFeedReferences,
    world_id: str,
    post_id: str,
    current_user_id: str,
    offset: int | None = None,
) -> ManualSocialFeedRead:
    """Read one root post and visible replies inside an exact World scope."""

    actor, _character = _owner_actor(
        references, world_id=world_id, current_user_id=current_user_id
    )
    root = queries.resolve_visible_root(db, world_id=world_id, post_id=post_id)
    if root is None:
        raise ManualSocialNotFoundError("post_not_in_world")
    replies, page_offset, next_offset = queries.list_visible_replies(
        db, world_id=world_id, root=root, offset=offset or 0,
        target_id=post_id if offset is None else None,
    )
    items = [root, *replies]
    reads = _post_reads(db, references=references, world_id=world_id,
        posts=items, viewer_world_character_id=actor.id)
    return ManualSocialFeedRead(
        world_id=world_id,
        root_post_id=root.id,
        target_post_id=post_id,
        page_offset=page_offset,
        next_offset=next_offset,
        owner_world_character_id=actor.id,
        items=[item.model_copy(update={"thread_root_post_id": root.id}) for item in reads],
    )
