"""Bind resident context to the caller's existing transaction and Social flows."""
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, TypeGuard

from sqlalchemy.orm import Session

from app.domains.routines.contracts.context_reads import ContextFeed, ContextNotification
from app.domains.routines.models import AgentActivityLog
from app.domains.routines.repository import resident_context as own_queries
from app.domains.routines.service import activity_logs
from app.domains.social.models.posts import Notification, Post, ProfileFollow
from app.domains.social.repository import profiles
from app.domains.social.repository import resident_context as social_queries
from app.runtime.resident.context_references import SqlAlchemyResidentActionReferences


class SocialContextWorkflows(Protocol):
    def list_feed(self, db: Session, *, limit: int) -> ContextFeed: ...
    def list_resident_actionable_inbox_notifications(self, db: Session, *, character_id: str, allowed_actions: tuple[str, ...], limit: int) -> Sequence[ContextNotification]: ...
    def activity_result_text_for_prompt(self, result: str | None, reason: str | None = None) -> str: ...


class SqlAlchemyResidentContextReferences(SqlAlchemyResidentActionReferences):
    def __init__(self, db: Session, *, social: SocialContextWorkflows) -> None:
        super().__init__(db)
        self._social = social

    def list_feed(self, *, limit: int) -> ContextFeed:
        return self._social.list_feed(self._db, limit=limit)

    def list_actionable_inbox(self, *, character_id: str, allowed_actions: tuple[str, ...], limit: int) -> Sequence[ContextNotification]:
        return self._social.list_resident_actionable_inbox_notifications(
            self._db, character_id=character_id, allowed_actions=allowed_actions, limit=limit,
        )

    def thread_root_post_id(self, post_id: str) -> str | None:
        return social_queries._thread_root_post_id_for_prompt(self._db, post_id)

    def find_review_notification(self, *, notification_id: int, character_id: str) -> Notification | None:
        return social_queries.find_review_notification(
            self._db, notification_id=notification_id, character_id=character_id,
        )

    def list_recent_own_posts(self, *, character_id: str) -> list[Post]:
        return social_queries.list_recent_own_posts(self._db, character_id=character_id)

    def list_recent_activity(self, character_id: str, *, limit: int) -> list[AgentActivityLog]:
        return activity_logs.list_recent_activity(self._db, character_id, limit=limit)

    def activity_result_text(self, result: str | None, reason: str | None = None) -> str:
        return self._social.activity_result_text_for_prompt(result, reason)

    def list_unread_reply_notifications(self, *, character_id: str, limit: int) -> list[Notification]:
        return social_queries.list_unread_reply_notifications(self._db, character_id=character_id, limit=limit)

    def list_recent_reply_posts(self, *, since: datetime) -> list[Post]:
        return social_queries.list_recent_reply_posts(self._db, since=since)

    def latest_relationship_review_at(self, *, character_id: str) -> datetime | None:
        return own_queries.latest_relationship_review_at(self._db, character_id=character_id)

    def list_profile_following(self, *, character_id: str, limit: int) -> tuple[list[ProfileFollow], str | None]:
        return profiles.list_profile_following(self._db, character_id=character_id, limit=limit)

    def list_recent_followed_posts(self, *, target_id: str, since: datetime) -> list[Post]:
        return social_queries.list_recent_followed_posts(self._db, target_id=target_id, since=since)

    def is_post_instance(self, value: object) -> TypeGuard[Post]:
        return isinstance(value, Post)
