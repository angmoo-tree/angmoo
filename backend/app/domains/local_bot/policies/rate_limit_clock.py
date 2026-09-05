"""Existing LocalBot local-day and positive Retry-After boundaries."""

from datetime import UTC, datetime, time, timedelta
from math import ceil

from app.domains.routines.service.tick_schedule import APP_TIMEZONE


def _remaining_seconds(
    latest: datetime | None, cooldown: timedelta, now: datetime
) -> int:
    if latest is None or cooldown <= timedelta(0):
        return 0
    ready_at = latest + cooldown
    return _seconds_until(ready_at, now) if ready_at > now else 0


def _local_day_start_utc(now: datetime) -> datetime:
    local_now = now.astimezone(APP_TIMEZONE)
    return datetime.combine(local_now.date(), time.min, tzinfo=APP_TIMEZONE).astimezone(
        UTC
    )


def _next_local_day_start_utc(now: datetime) -> datetime:
    return _local_day_start_utc(now + timedelta(days=1))


def _seconds_until(until: datetime, now: datetime) -> int:
    return max(1, ceil((until - now).total_seconds()))
