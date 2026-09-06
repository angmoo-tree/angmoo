"""Same-Session Social reads for Routines resident history; construction is IO-free."""

from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.social.models.posts import Post
from app.domains.routines.service import feed_history as history_policy
from app.domains.social.repository import (
    posts as post_repository,
    topic_history as topic_repository,
)
from app.domains.social.service import topic_metadata as topic_policy, activity_results
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.runtime.social.topic_metadata import RuntimeTopicHistoryReferences
from app.services import agent_briefs


class RuntimeFeedHistoryReferences:
    def get_post(self, db: Session, post_id: str) -> Post | None:
        return post_repository.get_post(db, post_id)

    def is_eligible(self, db: Session, *, character_id: str, post: Post) -> bool:
        return topic_policy._recent_feed_interest_post_is_eligible(
            db, character_id=character_id, post=post
        )

    def public_visible(self, db: Session, post: Post) -> bool:
        return _is_post_public_context_visible(db, post)

    def topic_metadata(
        self, db: Session, *, post: Post, character_id: str | None = None
    ) -> dict[str, str]:
        return topic_policy._topic_metadata_for_post(
            db,
            references=RuntimeTopicHistoryReferences(),
            post=post,
            character_id=character_id,
        )

    def recent_roots(
        self, db: Session, *, character_id: str, cutoff: datetime, limit: int
    ) -> list[Post]:
        return topic_repository.recent_own_root_posts(
            db, character_id=character_id, cutoff=cutoff, limit=limit
        )

    def body_preview(self, value: str | None) -> str:
        return activity_results._body_preview(value)

    def fallback_topic(self, *, title: str | None, body: str | None) -> str:
        return activity_results._fallback_topic_signature(title=title, body=body)

    def is_feed_theme(self, value: object) -> bool:
        return agent_briefs.is_feed_scan_community_theme_brief(value)


def format_feed_seed_consumed_sources_for_prompt(
    db: Session, *, character_id: str
) -> str:
    return history_policy.format_feed_seed_consumed_sources_for_prompt(
        db, references=RuntimeFeedHistoryReferences(), character_id=character_id
    )


def format_recent_feed_interest_history_for_prompt(
    db: Session, *, character_id: str
) -> str:
    return history_policy.format_recent_feed_interest_history_for_prompt(
        db, references=RuntimeFeedHistoryReferences(), character_id=character_id
    )


def format_recent_own_root_topic_history_for_prompt(
    db: Session, *, character_id: str
) -> str:
    return history_policy.format_recent_own_root_topic_history_for_prompt(
        db, references=RuntimeFeedHistoryReferences(), character_id=character_id
    )


def build_feed_history_sanitize_skeleton(
    db: Session, *, character_id: str
) -> dict[str, list[dict[str, str]]]:
    return history_policy.build_feed_history_sanitize_skeleton(
        db, references=RuntimeFeedHistoryReferences(), character_id=character_id
    )


def format_feed_history_metadata_fallback_for_prompt(
    db: Session, *, character_id: str
) -> dict[str, str]:
    return history_policy.format_feed_history_metadata_fallback_for_prompt(
        db, references=RuntimeFeedHistoryReferences(), character_id=character_id
    )


def maybe_log_feed_seed_consumed_for_created_post(
    db: Session, *, run: models.AgentRun, created_post_id: str
) -> models.AgentActivityLog | None:
    return history_policy.maybe_log_feed_seed_consumed_for_created_post(
        db,
        references=RuntimeFeedHistoryReferences(),
        run=run,
        created_post_id=created_post_id,
    )


def recent_own_root_topic_exists(
    db: Session, *, character_id: str, topic_signature: str | None
) -> bool:
    return history_policy.recent_own_root_topic_exists(
        db,
        references=RuntimeFeedHistoryReferences(),
        character_id=character_id,
        topic_signature=topic_signature,
    )
