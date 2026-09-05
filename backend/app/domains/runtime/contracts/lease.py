from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SchedulerLeaseState(StrEnum):
    STARTING = "starting"
    ACTIVE = "active"
    DRAINING = "draining"
    STOPPED = "stopped"
    FAILED = "failed"


class SchedulerTickResult(StrEnum):
    SUCCESS = "success"
    NO_ACTION = "no_action"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class SchedulerLeaseSnapshot:
    installation_id: str
    lease_owner_id: str | None
    fencing_epoch: int
    state: SchedulerLeaseState
    acquired_at: datetime | None
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    last_tick_window_at: datetime | None
    last_tick_started_at: datetime | None
    last_tick_finished_at: datetime | None
    last_tick_result: SchedulerTickResult | None
    next_tick_at: datetime | None
    last_error_code: str | None


@dataclass(frozen=True)
class SchedulerTickPermit:
    should_run: bool
    logical_window_at: datetime
    next_tick_at: datetime
    observed_gap_seconds: float
