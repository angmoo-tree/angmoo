"""Exact Social profile queries; preserve statement order and caller Session."""

from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.social.contracts.profile_activity import (
    WorldCharacterSocialProfileCounts,
    WorldCharacterSocialProfileForbiddenError,
    WorldCharacterSocialProfileMedia,
    WorldCharacterSocialProfileMention,
    WorldCharacterSocialProfileNotFoundError,
    WorldCharacterSocialProfilePage,
    WorldCharacterSocialProfilePost,
    WorldCharacterSocialProfileQuery,
    WorldCharacterSocialProfileValidationError,
)
from app.domains.social.models.posts import Post
from collections.abc import Iterable
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased
from app.domains.social.models.feed import WorldCharacterBlock
from app.domains.social.models.posts import PostLike, PostMedia
from app.domains.social.service.profile_cursor import _decode_cursor


class WorldProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _blocked_world_character_ids(
        self, world_id: str, viewer_ids: tuple[str, ...]
    ) -> frozenset[str]:
        if not viewer_ids:
            return frozenset()
        rows = self.db.execute(
            select(
                WorldCharacterBlock.blocker_world_character_id,
                WorldCharacterBlock.blocked_world_character_id,
            ).where(
                WorldCharacterBlock.world_id == world_id,
                or_(
                    WorldCharacterBlock.blocker_world_character_id.in_(viewer_ids),
                    WorldCharacterBlock.blocked_world_character_id.in_(viewer_ids),
                ),
            )
        ).all()
        blocked: set[str] = set()
        viewer_set = set(viewer_ids)
        for blocker_id, blocked_id in rows:
            if blocker_id in viewer_set:
                blocked.add(str(blocked_id))
            if blocked_id in viewer_set:
                blocked.add(str(blocker_id))
        return frozenset(blocked)

    def _counts(
        self, query: WorldCharacterSocialProfileQuery, blocked_ids: frozenset[str]
    ) -> WorldCharacterSocialProfileCounts:
        authored = (
            Post.world_id == query.world_id,
            Post.author_world_character_id == query.world_character_id,
            Post.visibility == "public",
            Post.deleted_at.is_(None),
            Post.report_hidden_at.is_(None),
        )
        post_count = self.db.scalar(
            select(func.count(Post.id)).where(
                *authored,
                Post.reply_to_post_id.is_(None),
                Post.repost_of_post_id.is_(None),
            )
        )
        parent = aliased(Post)
        reply_count_statement = (
            select(func.count(Post.id))
            .join(parent, parent.id == Post.reply_to_post_id)
            .where(
                *authored,
                Post.reply_to_post_id.is_not(None),
                parent.world_id == query.world_id,
                parent.visibility == "public",
                parent.deleted_at.is_(None),
                parent.report_hidden_at.is_(None),
            )
        )
        if blocked_ids:
            reply_count_statement = reply_count_statement.where(
                parent.author_world_character_id.not_in(blocked_ids)
            )
        reply_count = self.db.scalar(reply_count_statement)
        liked_post_statement = (
            select(func.count(PostLike.id))
            .join(Post, Post.id == PostLike.post_id)
            .outerjoin(parent, parent.id == Post.reply_to_post_id)
            .where(
                PostLike.world_id == query.world_id,
                PostLike.actor_world_character_id == query.world_character_id,
                Post.world_id == query.world_id,
                Post.visibility == "public",
                Post.deleted_at.is_(None),
                Post.report_hidden_at.is_(None),
                or_(
                    Post.reply_to_post_id.is_(None),
                    and_(
                        parent.world_id == query.world_id,
                        parent.visibility == "public",
                        parent.deleted_at.is_(None),
                        parent.report_hidden_at.is_(None),
                    ),
                ),
            )
        )
        if blocked_ids:
            liked_post_statement = liked_post_statement.where(
                Post.author_world_character_id.not_in(blocked_ids)
            )
        liked_post_count = self.db.scalar(liked_post_statement)
        received_like_statement = (
            select(func.count(PostLike.id))
            .join(Post, Post.id == PostLike.post_id)
            .outerjoin(parent, parent.id == Post.reply_to_post_id)
            .where(
                PostLike.world_id == query.world_id,
                PostLike.target_world_character_id == query.world_character_id,
                Post.world_id == query.world_id,
                Post.author_world_character_id == query.world_character_id,
                Post.visibility == "public",
                Post.deleted_at.is_(None),
                Post.report_hidden_at.is_(None),
                Post.repost_of_post_id.is_(None),
                or_(
                    Post.reply_to_post_id.is_(None),
                    and_(
                        parent.world_id == query.world_id,
                        parent.visibility == "public",
                        parent.deleted_at.is_(None),
                        parent.report_hidden_at.is_(None),
                    ),
                ),
            )
        )
        if blocked_ids:
            received_like_statement = received_like_statement.where(
                PostLike.actor_world_character_id.not_in(blocked_ids),
                or_(
                    Post.reply_to_post_id.is_(None),
                    parent.author_world_character_id.not_in(blocked_ids),
                ),
            )
        received_like_count = self.db.scalar(received_like_statement)
        return WorldCharacterSocialProfileCounts(
            post_count=int(post_count or 0),
            reply_count=int(reply_count or 0),
            liked_post_count=int(liked_post_count or 0),
            received_like_count=int(received_like_count or 0),
        )

    def _authored_posts(
        self, query: WorldCharacterSocialProfileQuery, blocked_ids: frozenset[str]
    ) -> tuple[list[Post], list[tuple[datetime, str]]]:
        statement = select(Post).where(
            Post.world_id == query.world_id,
            Post.author_world_character_id == query.world_character_id,
            Post.visibility == "public",
            Post.deleted_at.is_(None),
            Post.report_hidden_at.is_(None),
        )
        if query.tab == "posts":
            statement = statement.where(
                Post.reply_to_post_id.is_(None), Post.repost_of_post_id.is_(None)
            )
        else:
            parent = aliased(Post)
            statement = statement.join(
                parent, parent.id == Post.reply_to_post_id
            ).where(
                Post.reply_to_post_id.is_not(None),
                parent.world_id == query.world_id,
                parent.visibility == "public",
                parent.deleted_at.is_(None),
                parent.report_hidden_at.is_(None),
            )
            if blocked_ids:
                statement = statement.where(
                    parent.author_world_character_id.not_in(blocked_ids)
                )
        cursor = _decode_cursor(query)
        if cursor is not None:
            created_at, post_id = cursor
            statement = statement.where(
                or_(
                    Post.created_at < created_at,
                    and_(Post.created_at == created_at, Post.id < post_id),
                )
            )
        posts = list(
            self.db.scalars(
                statement.order_by(Post.created_at.desc(), Post.id.desc()).limit(
                    query.limit + 1
                )
            )
        )
        return (posts, [(post.created_at, post.id) for post in posts])

    def _liked_posts(
        self, query: WorldCharacterSocialProfileQuery, blocked_ids: frozenset[str]
    ) -> tuple[list[Post], list[tuple[datetime, str]]]:
        parent = aliased(Post)
        statement = (
            select(PostLike, Post)
            .join(Post, Post.id == PostLike.post_id)
            .outerjoin(parent, parent.id == Post.reply_to_post_id)
            .where(
                PostLike.world_id == query.world_id,
                PostLike.actor_world_character_id == query.world_character_id,
                Post.world_id == query.world_id,
                Post.visibility == "public",
                Post.deleted_at.is_(None),
                Post.report_hidden_at.is_(None),
                or_(
                    Post.reply_to_post_id.is_(None),
                    and_(
                        parent.world_id == query.world_id,
                        parent.visibility == "public",
                        parent.deleted_at.is_(None),
                        parent.report_hidden_at.is_(None),
                    ),
                ),
            )
        )
        if blocked_ids:
            statement = statement.where(
                Post.author_world_character_id.not_in(blocked_ids)
            )
        cursor = _decode_cursor(query)
        if cursor is not None:
            created_at, like_id = cursor
            try:
                like_id_value = int(like_id)
            except ValueError as exc:
                raise WorldCharacterSocialProfileValidationError() from exc
            statement = statement.where(
                or_(
                    PostLike.created_at < created_at,
                    and_(
                        PostLike.created_at == created_at, PostLike.id < like_id_value
                    ),
                )
            )
        rows = self.db.execute(
            statement.order_by(PostLike.created_at.desc(), PostLike.id.desc()).limit(
                query.limit + 1
            )
        ).all()
        posts = [row[1] for row in rows]
        cursor_values = [(row[0].created_at, str(row[0].id)) for row in rows]
        return (posts, cursor_values)

    def reply_counts(
        self, *, world_id: str, post_ids: list[str], blocked_ids: frozenset[str]
    ) -> dict[str, int]:
        reply_counts_statement = select(
            Post.reply_to_post_id, func.count(Post.id)
        ).where(
            Post.world_id == world_id,
            Post.reply_to_post_id.in_(post_ids),
            Post.visibility == "public",
            Post.deleted_at.is_(None),
            Post.report_hidden_at.is_(None),
        )
        if blocked_ids:
            reply_counts_statement = reply_counts_statement.where(
                Post.author_world_character_id.not_in(blocked_ids)
            )
        reply_counts = {
            str(post_id): int(count)
            for post_id, count in self.db.execute(
                reply_counts_statement.group_by(Post.reply_to_post_id)
            ).all()
            if post_id is not None
        }
        return reply_counts

    def like_counts(
        self, *, world_id: str, post_ids: list[str], blocked_ids: frozenset[str]
    ) -> dict[str, int]:
        like_counts_statement = select(PostLike.post_id, func.count(PostLike.id)).where(
            PostLike.world_id == world_id, PostLike.post_id.in_(post_ids)
        )
        if blocked_ids:
            like_counts_statement = like_counts_statement.where(
                PostLike.actor_world_character_id.not_in(blocked_ids)
            )
        like_counts = {
            str(post_id): int(count)
            for post_id, count in self.db.execute(
                like_counts_statement.group_by(PostLike.post_id)
            ).all()
        }
        return like_counts

    def media(self, post_ids: list[str]) -> Iterable[PostMedia]:
        return self.db.scalars(
            select(PostMedia)
            .where(PostMedia.post_id.in_(post_ids))
            .order_by(PostMedia.post_id.asc(), PostMedia.id.asc())
        )
