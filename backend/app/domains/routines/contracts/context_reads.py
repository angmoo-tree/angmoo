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



from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.domains.routines.contracts.planning_context import ClipContextText
from app.domains.routines.contracts.resident_prompts import ResidentPromptContext
from app.domains.routines.contracts.writer_results import JsonContextBuilder


class FeedCueView(Protocol):
    id: str
    topic: str


class ResidentReadContext(ResidentPromptContext, Protocol):
    activity_daypart: str
    memory_session_key: str | None
    daypart_start_date: date | None
    feed_cue: FeedCueView | None


HistoryReader = Callable[[ResidentReadContext], list[dict[str, Any]]]


class ReplyExistenceReader(Protocol):
    def __call__(
        self, db: Session, *, character_id: str, post_id: str | None
    ) -> bool: ...


@dataclass(frozen=True)
class RelationshipContextWorkflows:
    clip: ClipContextText
    history: HistoryReader
    history_prompt: HistoryReader
    following: Callable[[ResidentReadContext, str | None], bool]
    already_replied: ReplyExistenceReader


class TopicPromptBuilder(Protocol):
    def __call__(
        self, value: dict[str, Any] | None, *, current_date: date | None = None
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class WritingContextWorkflows:
    clip: ClipContextText
    coerce_topic_arc: JsonContextBuilder
    topic_arc_for_prompt: TopicPromptBuilder
    previous_handoff: Callable[[ResidentReadContext], dict[str, Any]]
    history_prompt: HistoryReader
    recent_own_posts: HistoryReader
    latest_summary: Callable[[ResidentReadContext], dict[str, Any] | None]
    seen_feed_posts: Callable[[ResidentReadContext], set[str]]
    seen_notifications: Callable[[ResidentReadContext], set[str]]


class ConversationPostView(Protocol):
    id: str
    author_name: str
    author_character_id: str | None
    body: str
    reply_to_post_id: str | None
    created_at: datetime


class ThreadRepliesReader(Protocol):
    def __call__(
        self, db: Session, post_id: str, *, limit: int
    ) -> list[ConversationPostView]: ...


@dataclass(frozen=True)
class ConversationWorkflows:
    clip: ClipContextText
    get_post: Callable[[Session, str | None], ConversationPostView | None]
    thread_replies: ThreadRepliesReader
