"""Narrow reads and identifiers used by resident action decisions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.domains.routines.contracts.planning_context import (
    ClipContextText,
    ResidentPlanningContext,
)


class UnfollowWatchReader(Protocol):
    def __call__(
        self, ctx: ResidentPlanningContext, *, target_id: str, reason_tag: str | None
    ) -> bool: ...


@dataclass(frozen=True)
class ActionPlanningWorkflows:
    clip: ClipContextText
    target_following: Callable[[ResidentPlanningContext, str | None], bool]
    has_unfollow_watch: UnfollowWatchReader
    yesterday_handoff: Callable[[ResidentPlanningContext], dict[str, Any]]


class ActionBudgetSettings(Protocol):
    allow_reply: bool
    allow_post: bool
    max_comments_per_day: int | None
    max_posts_per_day: int | None


class PostAuthorView(Protocol):
    author_character_id: str | None


class DailyActionCounter(Protocol):
    def __call__(
        self, db: Session, *, character_id: str, action: str, now: datetime
    ) -> int: ...


class ReplyTaskIdentifier(Protocol):
    def __call__(self, *, scope: str, index: int, post_id: str) -> str: ...


@dataclass(frozen=True)
class ActionBudgetWorkflows:
    ensure_setting: Callable[[Session, str], ActionBudgetSettings]
    count_today: DailyActionCounter
    get_post: Callable[[Session, str], PostAuthorView | None]
    reply_task_id: ReplyTaskIdentifier
