"""Existing Social and activity values read while preparing resident context."""
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, TypeGuard

from app.domains.routines.contracts.action_context import ActionPost, ResidentActionReferences


class ContextPost(ActionPost, Protocol):
    post_type: str
    created_at: datetime


class FeedPost(ContextPost, Protocol):
    repost_of_post_id: str | None
    author_name: str
    like_count: int
    reply_count: int
    repost_count: int


class ContextFeed(Protocol):
    items: Sequence[FeedPost]


class ContextNotification(Protocol):
    id: int
    source_post_id: str | None
    post_id: str | None
    actor_user_id: str | None
    actor_character_id: str | None
    created_at: datetime


class ContextActivityLog(Protocol):
    created_at: datetime
    action_type: str
    result: str
    reason: str


class ContextFollow(Protocol):
    target_character_id: str | None
    created_at: datetime


class ResidentContextReferences(ResidentActionReferences, Protocol):
    def get_post(self, post_id: str) -> ContextPost | None: ...
    def list_feed(self, *, limit: int) -> ContextFeed: ...
    def list_actionable_inbox(self, *, character_id: str, allowed_actions: tuple[str, ...], limit: int) -> Sequence[ContextNotification]: ...
    def thread_root_post_id(self, post_id: str) -> str | None: ...
    def find_review_notification(self, *, notification_id: int, character_id: str) -> ContextNotification | None: ...
    def list_recent_own_posts(self, *, character_id: str) -> Sequence[ContextPost]: ...
    def list_recent_activity(self, character_id: str, *, limit: int) -> Sequence[ContextActivityLog]: ...
    def activity_result_text(self, result: str | None, reason: str | None = None) -> str: ...
    def list_unread_reply_notifications(self, *, character_id: str, limit: int) -> Sequence[ContextNotification]: ...
    def list_recent_reply_posts(self, *, since: datetime) -> Sequence[ContextPost]: ...
    def latest_relationship_review_at(self, *, character_id: str) -> datetime | None: ...
    def list_profile_following(self, *, character_id: str, limit: int) -> tuple[Sequence[ContextFollow], str | None]: ...
    def list_recent_followed_posts(self, *, target_id: str, since: datetime) -> Sequence[ContextPost]: ...
    def is_post_instance(self, value: object) -> TypeGuard[ContextPost]: ...
