"""Bind other-owner writes without changing the caller's Session or transaction."""
from datetime import datetime
from typing import Literal
from sqlalchemy.orm import Session
from app.domains.routines.service import activity_logs as agent_crud
from app.services import community_abuse_quota
from app.runtime.relationships import sqlalchemy_social_event
from app.domains.social.service.timeline import SocialTimelineService


class RuntimeSocialWriteWorkflows:
    def log_activity(self, db: Session, *, user_id: str, character_id: str, action_type: str, target_post_id: str | None, reason: str, result: str) -> object:
        return agent_crud.log_activity(db, user_id=user_id, character_id=character_id, action_type=action_type, target_post_id=target_post_id, reason=reason, result=result)

    def consume_quota(self, db: Session, *, user_id: str, action: str) -> None:
        community_abuse_quota.consume(db, user_id=user_id, action=action)

    def exclude_events_for_posts(self, db: Session, *, post_ids: list[str], reason: Literal["source_deleted", "source_hidden"], invalidated_at: datetime) -> int:
        return sqlalchemy_social_event.exclude_events_for_posts(db, post_ids=post_ids, reason=reason, invalidated_at=invalidated_at)


timeline_service = SocialTimelineService(RuntimeSocialWriteWorkflows())
