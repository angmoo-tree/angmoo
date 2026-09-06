"""Only the owner reads and original activity logger used by LocalBot limits."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from app.domains.local_bot.contracts.authentication import LocalBotContext


class RateLimitReads(Protocol):
    def recent_root_post_at(
        self, db: Session, context: LocalBotContext, *, now: datetime
    ) -> datetime | None: ...
    def count_root_posts_since(
        self, db: Session, context: LocalBotContext, *, day_start: datetime
    ) -> int | None: ...
    def latest_root_post_at(
        self, db: Session, context: LocalBotContext
    ) -> datetime | None: ...
    def root_post_usage_since(
        self, db: Session, context: LocalBotContext, *, day_start: datetime
    ) -> int | None: ...
    def reaction_usage_since(
        self, db: Session, context: LocalBotContext, *, day_start: datetime
    ) -> int | None: ...
    def recent_activity_at(
        self,
        db: Session,
        context: LocalBotContext,
        *,
        action_types: tuple[str, ...],
        now: datetime,
        cooldown: timedelta,
    ) -> datetime | None: ...
    def activity_usage_since(
        self,
        db: Session,
        context: LocalBotContext,
        *,
        action_types: tuple[str, ...],
        day_start: datetime,
    ) -> int | None: ...
    def recent_rate_limit_log_id(
        self, db: Session, context: LocalBotContext, *, now: datetime, label: str
    ) -> int | None: ...
    def _latest_activity_at(
        self, db: Session, context: LocalBotContext, *, action_types: tuple[str, ...]
    ) -> datetime | None: ...
    def _count_activities_today(
        self,
        db: Session,
        context: LocalBotContext,
        *,
        action_types: tuple[str, ...],
        day_start: datetime,
    ) -> int: ...


class RateLimitLog(Protocol):
    def __call__(
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


@dataclass(frozen=True)
class RateLimitWorkflows:
    reads: RateLimitReads
    log_activity: RateLimitLog
