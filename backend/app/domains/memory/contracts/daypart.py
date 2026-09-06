"""Read-only inputs supplied by the resident execution owner.

The caller keeps its Session and attached objects. These protocols describe only
the fields used by Memory; they do not import the execution or Character ORM.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Generic, Protocol, TypeVar

SessionT = TypeVar("SessionT")


class DaypartCharacter(Protocol):
    id: str
    name: str


class DaypartRun(Protocol):
    id: str
    character_id: str
    gateway_result: Any


class DaypartContext(Protocol[SessionT]):
    db: SessionT
    character: DaypartCharacter
    memory_session_key: str | None
    daypart_start_date: date | None
    activity_daypart: str | None
    run_id: str
    run_started_at: datetime


class DaypartEvent(Protocol):
    id: int
    event_type: str
    memory_session_key: str
    daypart_start_date: date
    activity_daypart: str
    source_post_id: str | None
    notification_id: int | None
    topic_signature: str | None
    summary: str
    payload: Any
    provided_at: datetime


@dataclass(frozen=True)
class DaypartObservationReferences(Generic[SessionT]):
    # Same-Session author lookup occurs at the original observation position,
    # including after the first inbox event has committed.
    post_author: Callable[[SessionT, str | None, str | None], str | None]
    clip_text: Callable[[str | None, int], str]
