from __future__ import annotations
from datetime import UTC, datetime, timedelta
from app.domains.runtime.contracts.lease import SchedulerTickPermit


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
