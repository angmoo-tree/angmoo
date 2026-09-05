"""Deterministic due-tick decisions for activity windows."""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
from app.domains.routines.contracts.lifecycle import DueTick
from app.domains.routines.exceptions import ActivityRuntimeValidationError


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def latest_due_tick(
    *,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
    activity_interval_minutes: int,
    last_scheduled_for: datetime | None = None,
) -> DueTick | None:
    """Return only the newest due tick; older ticks are counted, never replayed."""

    if not 30 <= activity_interval_minutes <= 1440:
        raise ActivityRuntimeValidationError("activity_interval_out_of_range")
    start = aware_utc(window_start)
    end = aware_utc(window_end)
    current = aware_utc(now)
    if start >= end:
        raise ActivityRuntimeValidationError("plan_item_window_invalid")
    if current < start or current >= end:
        return None

    interval = timedelta(minutes=activity_interval_minutes)
    latest_index = int((current - start) // interval)
    first_unhandled_index = 0
    if last_scheduled_for is not None:
        previous = aware_utc(last_scheduled_for)
        if previous >= start:
            first_unhandled_index = int((previous - start) // interval) + 1
    if latest_index < first_unhandled_index:
        return None
    return DueTick(
        scheduled_for=start + (latest_index * interval),
        skipped_tick_count=latest_index - first_unhandled_index,
    )


__all__ = ['aware_utc', 'latest_due_tick']
