"""Exact Social source and idempotency lookups in the caller's Session."""

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.models.posts import Post
from app.domains.social.models.subjective_context import SocialActionSubjectiveContext


def get_source_post(db: Session, post_id: str) -> Post | None:
    return db.get(Post, post_id)


def find_for_execution(
    db: Session, execution_id: int
) -> SocialActionSubjectiveContext | None:
    return db.scalar(
        select(SocialActionSubjectiveContext).where(
            SocialActionSubjectiveContext.public_action_execution_id == execution_id
        )
    )
