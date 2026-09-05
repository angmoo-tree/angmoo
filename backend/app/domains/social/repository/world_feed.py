"""Canonical Social feed cursors, observations, blocks and reaction reads."""

from __future__ import annotations

from typing import Iterable
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from app.domains.social.contracts.world_feed import ReadySearchProfile
from app.domains.social.models.feed import (
    WorldCharacterFeedCursor,
    WorldCharacterFeedObservation,
    WorldCharacterBlock,
)
from app.domains.social.models.posts import Post, PostLike, PostRepost, ProfileFollow


def _existing_reactions(
    db: Session,
    *,
    actor: ReadySearchProfile,
    posts: Iterable[Post],
) -> tuple[set[str], set[str], set[str], set[str]]:
    post_list = list(posts)
    post_ids = [post.id for post in post_list]
    if not post_ids:
        return set(), set(), set(), set()
    liked = set(
        db.scalars(
            select(PostLike.post_id).where(
                PostLike.post_id.in_(post_ids),
                PostLike.character_id == actor.character.id,
            )
        )
    )
    commented = set(
        db.scalars(
            select(Post.reply_to_post_id).where(
                Post.reply_to_post_id.in_(post_ids),
                Post.author_world_character_id == actor.world_character.id,
                Post.deleted_at.is_(None),
            )
        )
    )
    reposted = set(
        db.scalars(
            select(PostRepost.post_id).where(
                PostRepost.post_id.in_(post_ids),
                PostRepost.character_id == actor.character.id,
            )
        )
    )
    author_character_ids = {
        post.author_character_id for post in post_list if post.author_character_id
    }
    followed = set(
        db.scalars(
            select(ProfileFollow.target_character_id).where(
                ProfileFollow.follower_character_id == actor.character.id,
                ProfileFollow.target_character_id.in_(author_character_ids),
            )
        )
    )
    return liked, commented, reposted, followed


def cursor_for_update(db: Session, *, world_character_id: str):
    return db.scalar(
        select(WorldCharacterFeedCursor)
        .where(WorldCharacterFeedCursor.world_character_id == world_character_id)
        .with_for_update()
    )


def observation_for_update(db: Session, *, observer_id: str, post_id: str):
    return db.scalar(
        select(WorldCharacterFeedObservation)
        .where(
            WorldCharacterFeedObservation.observer_world_character_id == observer_id,
            WorldCharacterFeedObservation.post_id == post_id,
        )
        .with_for_update()
    )


def is_blocked(db: Session, *, world_id: str, actor_id: str, author_id: str):
    return db.scalar(
        select(WorldCharacterBlock.id).where(
            WorldCharacterBlock.world_id == world_id,
            or_(
                and_(
                    WorldCharacterBlock.blocker_world_character_id == actor_id,
                    WorldCharacterBlock.blocked_world_character_id == author_id,
                ),
                and_(
                    WorldCharacterBlock.blocker_world_character_id == author_id,
                    WorldCharacterBlock.blocked_world_character_id == actor_id,
                ),
            ),
        )
    )


def get_post(db: Session, post_id: str) -> Post | None:
    return db.get(Post, post_id)


def get_cursor(db: Session, world_character_id: str) -> WorldCharacterFeedCursor | None:
    return db.get(WorldCharacterFeedCursor, world_character_id)


def observations_for_posts(db: Session, *, observer_id: str, post_ids: Iterable[str]):
    return db.scalars(
        select(WorldCharacterFeedObservation).where(
            WorldCharacterFeedObservation.observer_world_character_id == observer_id,
            WorldCharacterFeedObservation.post_id.in_(post_ids),
        )
    )


def recent_observations(db: Session, *, observer_id: str, recent_limit: int):
    return db.scalars(
        select(WorldCharacterFeedObservation)
        .where(WorldCharacterFeedObservation.observer_world_character_id == observer_id)
        .order_by(
            WorldCharacterFeedObservation.created_at.desc(),
            WorldCharacterFeedObservation.id.desc(),
        )
        .limit(max(1, min(recent_limit, 50)))
    )
