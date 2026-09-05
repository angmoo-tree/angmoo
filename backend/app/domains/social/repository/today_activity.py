"""Exact bounded Social post/block/declaration queries on one Session."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.domains.social.models.posts import Post
from app.domains.social.models.feed import WorldCharacterBlock
from app.domains.social.models.subjective_context import SocialActionSubjectiveContext
from app.domains.social.constants import MAX_TODAY_SOCIAL_SCAN, MAX_TODAY_QUERY_BATCH


class TodayActivityRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _bounded(self, statement):
        rows = self._db.scalars(
            statement.limit(MAX_TODAY_SOCIAL_SCAN + 1).execution_options(
                populate_existing=True
            )
        ).all()
        return rows[:MAX_TODAY_SOCIAL_SCAN], len(rows) > MAX_TODAY_SOCIAL_SCAN

    def _by_ids(self, model, column, identifiers):
        values, rows = sorted(set(identifiers)), []
        for offset in range(0, len(values), MAX_TODAY_QUERY_BATCH):
            rows.extend(
                self._db.scalars(
                    select(model)
                    .where(column.in_(values[offset : offset + MAX_TODAY_QUERY_BATCH]))
                    .execution_options(populate_existing=True)
                ).all()
            )
        return rows

    def _blocked_counterparts(self, world_id, subject_id):
        rows = self._db.scalars(
            select(WorldCharacterBlock).where(
                WorldCharacterBlock.world_id == world_id,
                or_(
                    WorldCharacterBlock.blocker_world_character_id == subject_id,
                    WorldCharacterBlock.blocked_world_character_id == subject_id,
                ),
            )
        ).all()
        return {
            row.blocked_world_character_id
            if row.blocker_world_character_id == subject_id
            else row.blocker_world_character_id
            for row in rows
        }

    def authored(self, world_id, subject_world_character_id, start, end):
        return self._bounded(
            select(Post)
            .where(
                Post.world_id == world_id,
                Post.author_world_character_id == subject_world_character_id,
                Post.created_at >= start,
                Post.created_at <= end,
            )
            .order_by(Post.created_at.desc(), Post.id)
        )

    def received(self, world_id, subject_world_character_id, start, end):
        subject_post_ids = select(Post.id).where(
            Post.world_id == world_id,
            Post.author_world_character_id == subject_world_character_id,
        )
        return self._bounded(
            select(Post)
            .where(
                Post.world_id == world_id,
                Post.created_at >= start,
                Post.created_at <= end,
                Post.reply_to_post_id.in_(subject_post_ids),
                Post.author_world_character_id != subject_world_character_id,
            )
            .order_by(Post.created_at.desc(), Post.id)
        )

    def posts(self, identifiers):
        return self._by_ids(Post, Post.id, identifiers)

    def subjective(self, event_ids):
        return self._by_ids(
            SocialActionSubjectiveContext,
            SocialActionSubjectiveContext.social_event_id,
            event_ids,
        )
