"""Activity lifecycle result records."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


EVENT_CONSUMPTION_NAMESPACE = "next_activity_beat"


@dataclass(frozen=True)
class RecoveryCounts:
    beats: int
    consumptions: int


@dataclass(frozen=True)
class DueTick:
    scheduled_for: datetime
    skipped_tick_count: int


@dataclass(frozen=True)
class DaypartTransitionCounts:
    completed: int
    skipped: int


@dataclass(frozen=True)
class WorldInterruptionCounts:
    interrupted: int
    cancelled: int


__all__ = ['RecoveryCounts', 'DueTick', 'DaypartTransitionCounts', 'WorldInterruptionCounts']


class LifecycleReferences(Protocol):
    """Same-Session owner reads; no permissions, state changes, or commits here."""
    def get_world_character(self, world_character_id: str) -> Any: ...
    def get_membership(self, membership_id: str) -> Any: ...
    def elapsed_autonomous_world_character_ids(self, *, now: datetime) -> list[str]: ...
