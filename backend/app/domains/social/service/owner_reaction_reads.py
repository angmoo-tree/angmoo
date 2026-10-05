"""Batched canonical owner context for World and global views; GET never repairs rows."""
from collections import defaultdict
from typing import TypedDict, TypeVar, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.social.contracts.manual_feed import ManualFeedReferences
from app.domains.social.models.posts import Post
from app.domains.social.schemas.community import FeedPage, PostDetail, PostThreadRead, PostSummary
from app.domains.social.service.manual_feed import _owner_actor
from app.domains.social.repository import manual_feed as queries
from app.domains.social.policies.owner_target import eligible_owner_target
from app.domains.social.contracts.writes import SocialWriteError
from app.domains.world_characters.contracts.owner_identity import OwnerControlledIdentityError


class OwnerReactionContext(TypedDict):
    viewer_like_state: Literal["liked", "not_liked"]
    can_owner_like: bool
    reaction_world_id: str
    reaction_owner_world_character_id: str


def read_owner_reactions(db: Session, *, references: ManualFeedReferences, posts: list[Post],
                         current_user_id: str | None) -> dict[str, OwnerReactionContext]:
    result: dict[str, OwnerReactionContext] = {}
    if not current_user_id:
        return result
    worlds: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        if post.world_id and post.author_world_character_id and post.visibility == "public" and post.deleted_at is None and post.report_hidden_at is None:
            worlds[post.world_id].append(post)
    for world_id, rows in worlds.items():
        try:
            actor, _ = _owner_actor(references, world_id=world_id, current_user_id=current_user_id)
        except (SocialWriteError, OwnerControlledIdentityError):
            continue
        author_ids = {post.author_world_character_id for post in rows}
        references.prepare_authors(world_id=world_id, author_ids=author_ids)
        blocked = queries.blocked_authors(db, world_id=world_id, viewer_id=actor.id, author_ids=author_ids)
        liked = queries.viewer_likes(db, world_id=world_id, viewer_id=actor.id, post_ids=[post.id for post in rows])
        for post in rows:
            target = references.get_world_character(post.author_world_character_id)
            membership = references.get_membership(target.membership_id) if target else None
            result[post.id] = dict(viewer_like_state="liked" if post.id in liked else "not_liked",
                can_owner_like=eligible_owner_target(target=target, membership=membership, world_id=world_id, actor_id=actor.id,
                    blocked=post.author_world_character_id in blocked),
                reaction_world_id=world_id, reaction_owner_world_character_id=actor.id)
    return result


PublicRead = TypeVar("PublicRead", FeedPage, PostThreadRead, PostDetail)


def enrich_public_reactions(db: Session, *, references: ManualFeedReferences, read: PublicRead,
                            current_user_id: str | None) -> PublicRead:
    """The router supplies the caller Session and typed read references."""
    views: list[PostSummary | PostDetail]
    if isinstance(read, FeedPage):
        views = list(read.items)
    elif isinstance(read, PostThreadRead):
        views = [read.post, *read.replies]
    else:
        views = [read]
    posts = list(db.scalars(select(Post).where(Post.id.in_([item.id for item in views]))))
    context = read_owner_reactions(db, references=references, posts=posts, current_user_id=current_user_id)
    for item in views:
        for key, value in context.get(item.id, {}).items():
            setattr(item, key, value)
    return read
