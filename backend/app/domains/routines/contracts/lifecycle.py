"""Activity lifecycle result records."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


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
