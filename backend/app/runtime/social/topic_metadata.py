"""Bind Social topic fallback to the caller-owned Routines creation log query."""

from __future__ import annotations
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.service import topic_metadata as topic_policy
from app.domains.routines.repository import feed_history as log_repository
from app.domains.routines.models import AgentActivityLog


class RuntimeTopicHistoryReferences:
    def latest_creation_log(
        self, db: Session, *, character_id: str, post_id: str
    ) -> AgentActivityLog | None:
        return log_repository.latest_post_created_log(
            db, character_id=character_id, post_id=post_id
        )


def _latest_post_created_topic_metadata(
    db: Session, *, character_id: str | None, post_id: str
) -> dict[str, str]:
    return topic_policy._latest_post_created_topic_metadata(
        db,
        references=RuntimeTopicHistoryReferences(),
        character_id=character_id,
        post_id=post_id,
    )


def _topic_metadata_for_post(
    db: Session, *, post: models.Post, character_id: str | None = None
) -> dict[str, str]:
    return topic_policy._topic_metadata_for_post(
        db,
        references=RuntimeTopicHistoryReferences(),
        post=post,
        character_id=character_id,
    )


def post_topic_signature_for_prompt(db: Session, post: models.Post) -> str:
    return topic_policy.post_topic_signature_for_prompt(
        db, post, references=RuntimeTopicHistoryReferences()
    )
