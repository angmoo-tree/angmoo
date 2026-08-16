from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


SCHEDULER_SINGLETON_KEY = "resident-tick-scheduler"


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


class SchedulerLeaseError(RuntimeError):
    reason_code = "scheduler_lease_error"


class SchedulerLeaseHeldError(SchedulerLeaseError):
    reason_code = "scheduler_lease_held"


class SchedulerLeaseLostError(SchedulerLeaseError):
    reason_code = "scheduler_lease_lost"


class SchedulerFenceRejectedError(SchedulerLeaseLostError):
    reason_code = "scheduler_fence_rejected"


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


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def logical_tick_window(now: datetime, *, interval_seconds: int) -> datetime:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    current = aware_utc(now)
    epoch_seconds = int(current.timestamp())
    floored = epoch_seconds - (epoch_seconds % interval_seconds)
    return datetime.fromtimestamp(floored, tz=UTC)


def decide_tick_window(
    *,
    now: datetime,
    interval_seconds: int,
    last_tick_window_at: datetime | None,
    last_observed_at: datetime | None,
) -> SchedulerTickPermit:
    current = aware_utc(now)
    window = logical_tick_window(current, interval_seconds=interval_seconds)
    previous_window = (
        aware_utc(last_tick_window_at) if last_tick_window_at is not None else None
    )
    previous_observed = (
        aware_utc(last_observed_at) if last_observed_at is not None else None
    )
    observed_gap = (
        max(0.0, (current - previous_observed).total_seconds())
        if previous_observed is not None
        else 0.0
    )
    return SchedulerTickPermit(
        should_run=previous_window is None or window > previous_window,
        logical_window_at=window,
        next_tick_at=window + timedelta(seconds=interval_seconds),
        observed_gap_seconds=observed_gap,
    )
