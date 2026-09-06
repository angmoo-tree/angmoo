"""Readonly resident/identity facts used to authorize Social tool calls.

Implementations preserve the same attached objects and Session. Only the exact
activity denial exception is translated; unrelated failures keep propagating.
"""

from datetime import datetime
from typing import Protocol
from app.domains.social.contracts.topic_history import (
    CreationTopicLog,
    TopicHistoryReferences,
)
from sqlalchemy.orm import Session


class ToolRun(Protocol):
    @property
    def created_at(self) -> datetime: ...
    @property
    def id(self) -> str: ...
    @property
    def user_id(self) -> str: ...
    @property
    def character_id(self) -> str: ...
    @property
    def post_id(self) -> str | None: ...
    @property
    def status(self) -> str: ...


class ToolUser(Protocol):
    @property
    def id(self) -> str: ...


class AgentToolReferences(Protocol):
    @property
    def activity_policy_denied(self) -> type[Exception]: ...
    def get_active_run_for_tool_auth_key(
        self, db: Session, key: str
    ) -> ToolRun | None: ...
    def get_active_run_for_session(self, db: Session, key: str) -> ToolRun | None: ...
    def get_latest_run_for_tool_auth_key(
        self, db: Session, key: str
    ) -> ToolRun | None: ...
    def get_latest_run_for_session(self, db: Session, key: str) -> ToolRun | None: ...
    def get_user(self, db: Session, user_id: str) -> ToolUser | None: ...
    def assert_action_allowed(
        self, db: Session, *, run: ToolRun, action: str
    ) -> None: ...


class PendingFeedCue(Protocol):
    @property
    def id(self) -> int: ...


class AgentToolActionWorkflows(AgentToolReferences, Protocol):
    def log_activity(
        self,
        db: Session,
        *,
        user_id: str,
        character_id: str,
        action_type: str,
        target_post_id: str | None,
        reason: str,
        result: str,
    ) -> object: ...
    def get_pending_feed_cue(
        self, db: Session, character_id: str
    ) -> PendingFeedCue | None: ...
    def mark_pending_feed_cue_used(
        self, db: Session, *, character_id: str, run_id: str, post_id: str
    ) -> None: ...
    def maybe_log_feed_seed_consumed_for_created_post(
        self, db: Session, *, run: ToolRun, created_post_id: str
    ) -> None: ...


class ToolActivityPolicy(Protocol):
    @property
    def allowed_actions(self) -> tuple[str, ...]: ...


class AgentToolReadWorkflows(AgentToolReferences, Protocol):
    @property
    def topic_history(self) -> TopicHistoryReferences: ...
    def build_activity_policy(
        self, db: Session, *, character_id: str
    ) -> ToolActivityPolicy: ...
    def inbox_delivery_logs(
        self, db: Session, *, run: ToolRun
    ) -> list[CreationTopicLog]: ...
    def log_activity(
        self,
        db: Session,
        *,
        user_id: str,
        character_id: str,
        action_type: str,
        target_post_id: str | None,
        reason: str,
        result: str,
    ) -> object: ...
