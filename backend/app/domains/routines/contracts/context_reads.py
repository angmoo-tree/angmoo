"""Existing values and owner reads used to prepare resident activity context."""

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
