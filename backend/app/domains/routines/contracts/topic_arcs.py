"""The role value needed to validate an ordered TopicArc."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.domains.routines.contracts.planning_context import ResidentClockContext


class TopicArcStepRole(Protocol):
    role: str


class TopicArcCharacter(Protocol):
    id: str


class TopicArcContext(ResidentClockContext, Protocol):
    db: Session
    run_id: str
    character: TopicArcCharacter


class TopicArcEvent(Protocol):
    provided_at: datetime | None


@dataclass(frozen=True)
class TopicArcWorkflows:
    """Existing clip and nullable reads; callbacks keep the caller's Session."""

    clip: Callable[[Any, int], str]
    last_post_created_at: Callable[[TopicArcContext, str | None], datetime | None]
    latest_event: Callable[[TopicArcContext, str | None], TopicArcEvent | None]
