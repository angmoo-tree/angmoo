"""Owner feed/thread visibility, profile capability and response composition."""
from __future__ import annotations
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.schemas.manual import ManualSocialFeedRead, ManualSocialPostRead, ManualSocialThreadRead, ManualSocialParentRead
from app.domains.social.contracts.actors import SocialCharacter
from app.domains.social.contracts.manual_feed import ManualFeedReferences, ManualFeedWorldCharacter
from app.domains.social.contracts.writes import SocialWriteConflictError as ManualSocialConflictError, SocialWriteForbiddenError as ManualSocialForbiddenError, SocialWriteNotFoundError as ManualSocialNotFoundError
from app.domains.social.repository import manual_feed as queries, event_evidence as post_queries
from app.domains.social.service.post_attachments import media_view
from app.domains.social.policies.owner_target import eligible_owner_target
from app.domains.social.contracts.post_authors import WorldPostAuthor


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
    viewer_liked: bool = False,
    author_profiles: dict[str, WorldPostAuthor] | None = None,
) -> ManualSocialPostRead:
    if post.world_id is None or post.author_world_character_id is None:
        raise ManualSocialConflictError("world_post_scope_missing")
    author = references.get_world_character(post.author_world_character_id)
    author_character = references.get_character(author.character_id) if author is not None else None
    profile = (author_profiles or {}).get(post.author_world_character_id)
    if profile is not None and (profile.world_id != post.world_id or profile.character_id != post.author_character_id
        or author_character is None or author_character.deleted_at is not None):
        profile = None
    author_profile_available = _author_profile_available(
        db,
        references=references,
        world_id=post.world_id,
        author_world_character_id=post.author_world_character_id,
        viewer_world_character_id=viewer_world_character_id,
        blocked_author_ids=blocked_author_ids,
    )
    eligible = eligible_owner_target(target=author, membership=references.get_membership(author.membership_id) if author else None,
        world_id=post.world_id, actor_id=viewer_world_character_id, blocked=post.author_world_character_id in blocked_author_ids)
    return ManualSocialPostRead(
        id=post.id,
        world_id=post.world_id,
        author_world_character_id=post.author_world_character_id,
        author_name=profile.display_name if profile is not None else post.author_name,
        author_handle=profile.handle if profile is not None else None,
        author_avatar_url=profile.avatar_url if profile is not None else None,
        title=post.title,
        body=post.body,
        media=[media_view(row) for row in post.media],
        post_type=post.post_type,
        reply_to_post_id=post.reply_to_post_id,
        created_at=post.created_at,
        reply_count=reply_count,
        like_count=like_count,
        author_profile_capability=(
            "available" if author_profile_available else "unavailable"
        ),
        can_owner_reply=eligible,
        viewer_like_state="liked" if viewer_liked else "not_liked",
        can_owner_like=eligible,
        reaction_world_id=post.world_id,
        reaction_owner_world_character_id=viewer_world_character_id,
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
    author_profiles = references.author_profiles(world_id=world_id, author_ids=author_ids)
    blocked = queries.blocked_authors(db, world_id=world_id, viewer_id=viewer_world_character_id, author_ids=author_ids)

    reply_counts = queries.reply_counts(db, world_id=world_id, post_ids=post_ids, viewer_id=viewer_world_character_id)
    like_counts = queries.like_counts(db, post_ids=post_ids)
    liked = queries.viewer_likes(db, world_id=world_id, viewer_id=viewer_world_character_id, post_ids=post_ids)
    return [
        _post_read(
            db,
            post,
            references=references,
            reply_count=reply_counts.get(post.id, 0),
            like_count=like_counts.get(post.id, 0),
            viewer_world_character_id=viewer_world_character_id,
            blocked_author_ids=blocked,
            viewer_liked=post.id in liked,
            author_profiles=author_profiles,
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
    # Feed v1 retains public posts; blocking disables profile/reaction
    # capabilities. The selected-thread v2 reader separately filters replies.
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
) -> ManualSocialThreadRead:
    """The selected post is the stable subtree anchor on every page."""

    actor, _character = _owner_actor(
        references, world_id=world_id, current_user_id=current_user_id
    )
    selected = queries.visible_post(db, world_id=world_id, post_id=post_id)
    root_id = queries.canonical_root_id(db, world_id=world_id, post_id=post_id)
    if selected is None or root_id is None or selected.author_world_character_id in queries.blocked_authors(db,
        world_id=world_id, viewer_id=actor.id, author_ids={selected.author_world_character_id}):
        raise ManualSocialNotFoundError("post_not_in_world")
    replies, page_offset, next_offset = queries.list_visible_replies(
        db, world_id=world_id, root=selected, offset=offset or 0, viewer_id=actor.id,
    )
    items = [selected, *replies]
    reads = _post_reads(db, references=references, world_id=world_id,
        posts=items, viewer_world_character_id=actor.id)
    references_by_id = []
    parent_ids = {post.reply_to_post_id for post in items if post.reply_to_post_id}
    available_parent_ids = queries.visible_parent_ids(db, world_id=world_id, post_ids=parent_ids, viewer_id=actor.id)
    for parent_id in sorted(parent_ids):
        references_by_id.append(ManualSocialParentRead(post_id=parent_id,
            state="available" if parent_id in available_parent_ids else "unavailable"))
    return ManualSocialThreadRead(
        world_id=world_id,
        root_post_id=root_id,
        selected_post=reads[0].model_copy(update={"thread_root_post_id": root_id}),
        parent=next((item for item in references_by_id if item.post_id == selected.reply_to_post_id), None),
        parent_references=references_by_id,
        page_offset=page_offset,
        next_offset=next_offset,
        owner_world_character_id=actor.id,
        replies=[item.model_copy(update={"thread_root_post_id": root_id}) for item in reads[1:]],
    )
