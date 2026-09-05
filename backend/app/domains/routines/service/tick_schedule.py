from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.core import active_hours
from app.config import settings


APP_TIMEZONE = ZoneInfo("Asia/Seoul")


class ActivityScheduleSetting(Protocol):
    activity_interval_minutes: int
    active_hours_start: str
    active_hours_end: str


@dataclass(frozen=True)
class TickSchedule:
    next_tick_at: datetime
    target_interval_seconds: int
    schedule_spread_seconds: int
    schedule_spread_reason: str


def tick_interval_seconds(setting: ActivityScheduleSetting) -> int:
    return max(30 * 60, min(setting.activity_interval_minutes, 1440) * 60)


def next_tick_schedule(
    setting: ActivityScheduleSetting,
    *,
    character_id: str,
    now: datetime,
    within_active_hours: bool,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> TickSchedule:
    current = aware_utc(now)
    target_interval = tick_interval_seconds(setting)
    if not within_active_hours:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current,
            reason="active_start_spread",
            target_interval_seconds=target_interval,
            timezone=timezone,
        )

    base = current + timedelta(seconds=target_interval)
    current_window = _active_window_containing(setting, current, timezone=timezone)
    if current_window is not None and base >= current_window[1]:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current_window[1],
            reason="next_window",
            target_interval_seconds=target_interval,
            timezone=timezone,
        )

    max_spread = settings.resident_tick_interval_jitter_max_seconds
    spread = _deterministic_spread_seconds(
        character_id,
        "interval_jitter",
        f"{base.astimezone(timezone).isoformat()}:{target_interval}",
        max_spread,
    )
    candidate = base + timedelta(seconds=spread)
    if current_window is not None and candidate >= current_window[1]:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current_window[1],
            reason="next_window",
            target_interval_seconds=target_interval,
            timezone=timezone,
        )
    return TickSchedule(
        next_tick_at=candidate,
        target_interval_seconds=target_interval,
        schedule_spread_seconds=spread,
        schedule_spread_reason="interval_jitter",
    )


def initial_tick_schedule(
    setting: ActivityScheduleSetting,
    *,
    character_id: str,
    now: datetime,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> TickSchedule:
    current = aware_utc(now)
    target_interval = tick_interval_seconds(setting)
    if not is_within_active_hours(setting, current, timezone=timezone):
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current,
            reason="active_start_spread",
            target_interval_seconds=target_interval,
            timezone=timezone,
        )

    max_spread = settings.resident_tick_initial_spread_seconds
    spread = _deterministic_spread_seconds(
        character_id,
        "initial_spread",
        current.astimezone(timezone).strftime("%Y-%m-%dT%H:%M"),
        max_spread,
    )
    candidate = current + timedelta(seconds=spread)
    current_window = _active_window_containing(setting, current, timezone=timezone)
    if current_window is not None and candidate >= current_window[1]:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current_window[1],
            reason="next_window",
            target_interval_seconds=target_interval,
            timezone=timezone,
        )
    return TickSchedule(
        next_tick_at=candidate,
        target_interval_seconds=target_interval,
        schedule_spread_seconds=spread,
        schedule_spread_reason="initial_spread",
    )


def retry_tick_schedule(
    setting: ActivityScheduleSetting,
    *,
    character_id: str,
    retry_at: datetime,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> TickSchedule:
    base = aware_utc(retry_at)
    target_interval = tick_interval_seconds(setting)
    if not is_within_active_hours(setting, base, timezone=timezone):
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=base,
            reason="retry_spread",
            target_interval_seconds=target_interval,
            timezone=timezone,
        )

    max_spread = settings.resident_tick_retry_spread_seconds
    spread = _deterministic_spread_seconds(
        character_id,
        "retry_spread",
        base.astimezone(timezone).strftime("%Y-%m-%dT%H:%M"),
        max_spread,
    )
    candidate = base + timedelta(seconds=spread)
    current_window = _active_window_containing(setting, base, timezone=timezone)
    if current_window is not None and candidate >= current_window[1]:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current_window[1],
            reason="retry_spread",
            target_interval_seconds=target_interval,
            timezone=timezone,
        )
    return TickSchedule(
        next_tick_at=candidate,
        target_interval_seconds=target_interval,
        schedule_spread_seconds=spread,
        schedule_spread_reason="retry_spread",
    )


def recovery_tick_schedule(
    setting: ActivityScheduleSetting,
    *,
    character_id: str,
    now: datetime,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> TickSchedule:
    current = aware_utc(now)
    target_interval = tick_interval_seconds(setting)
    max_spread = settings.resident_tick_retry_spread_seconds
    spread = _deterministic_spread_seconds(
        character_id,
        "recovery_spread",
        current.astimezone(timezone).strftime("%Y-%m-%dT%H:%M"),
        max_spread,
    )
    return TickSchedule(
        next_tick_at=current + timedelta(seconds=spread),
        target_interval_seconds=target_interval,
        schedule_spread_seconds=spread,
        schedule_spread_reason="recovery_spread",
    )


def is_within_active_hours(
    setting: ActivityScheduleSetting,
    now: datetime,
    *,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> bool:
    try:
        start, end = active_hours.active_hours_minutes(
            setting.active_hours_start,
            setting.active_hours_end,
        )
    except ValueError:
        return False
    if active_hours.active_hours_duration_from_minutes(start, end) <= 0:
        return False
    local_now = now.astimezone(timezone)
    minute = local_now.hour * 60 + local_now.minute
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _next_active_start(
    setting: ActivityScheduleSetting,
    now: datetime,
    *,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> datetime:
    window = _next_active_window(setting, now, timezone=timezone)
    if window is not None:
        return window[0]
    try:
        start = active_hours.parse_active_hour(
            setting.active_hours_start,
            allow_end_of_day=False,
        )
    except ValueError:
        start = active_hours.parse_active_hour(
            active_hours.DEFAULT_ACTIVE_HOURS_START,
            allow_end_of_day=False,
        )
    local_now = now.astimezone(timezone)
    minute = local_now.hour * 60 + local_now.minute
    candidate_date = local_now.date()
    if minute >= start:
        candidate_date = candidate_date + timedelta(days=1)
    start_hour = min(start // 60, 23)
    start_minute = 0 if start >= 24 * 60 else start % 60
    if start >= 24 * 60:
        candidate_date = candidate_date + timedelta(days=1)
    return datetime.combine(
        candidate_date, time(start_hour, start_minute), tzinfo=timezone
    ).astimezone(UTC)


def _active_start_schedule(
    setting: ActivityScheduleSetting,
    *,
    character_id: str,
    now: datetime,
    reason: str,
    target_interval_seconds: int,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> TickSchedule:
    window = _next_active_window(setting, now, timezone=timezone)
    if window is None:
        next_tick_at = _next_active_start(setting, now, timezone=timezone)
        return TickSchedule(
            next_tick_at=next_tick_at,
            target_interval_seconds=target_interval_seconds,
            schedule_spread_seconds=0,
            schedule_spread_reason=reason,
        )

    start_at, end_at = window
    max_spread = _active_start_spread_limit_seconds(setting, start_at, end_at)
    spread = _deterministic_spread_seconds(
        character_id,
        reason,
        start_at.astimezone(timezone).isoformat(),
        max_spread,
    )
    return TickSchedule(
        next_tick_at=start_at + timedelta(seconds=spread),
        target_interval_seconds=target_interval_seconds,
        schedule_spread_seconds=spread,
        schedule_spread_reason=reason,
    )


def _active_start_spread_limit_seconds(
    setting: ActivityScheduleSetting,
    start_at: datetime,
    end_at: datetime,
) -> int:
    configured = settings.resident_tick_active_start_spread_seconds
    window_seconds = max(0, int((end_at - start_at).total_seconds()) - 1)
    boundary_seconds = (30 * 60) - 1
    return max(0, min(configured, boundary_seconds, window_seconds))


def _active_window_containing(
    setting: ActivityScheduleSetting,
    now: datetime,
    *,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> tuple[datetime, datetime] | None:
    local_now = aware_utc(now).astimezone(timezone)
    start, _, duration = _active_hours_parts(setting)
    if duration <= 0:
        return None
    for day_offset in (-1, 0, 1):
        start_at = _local_datetime_for_minute(
            local_now.date() + timedelta(days=day_offset),
            start,
            timezone=timezone,
        )
        end_at = start_at + timedelta(minutes=duration)
        if start_at <= local_now < end_at:
            return start_at.astimezone(UTC), end_at.astimezone(UTC)
    return None


def _next_active_window(
    setting: ActivityScheduleSetting,
    now: datetime,
    *,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> tuple[datetime, datetime] | None:
    local_now = aware_utc(now).astimezone(timezone)
    start, _, duration = _active_hours_parts(setting)
    if duration <= 0:
        return None
    for day_offset in (-1, 0, 1, 2, 3):
        start_at = _local_datetime_for_minute(
            local_now.date() + timedelta(days=day_offset),
            start,
            timezone=timezone,
        )
        end_at = start_at + timedelta(minutes=duration)
        if end_at <= local_now:
            continue
        if start_at >= local_now or start_at <= local_now < end_at:
            return start_at.astimezone(UTC), end_at.astimezone(UTC)
    return None


def _active_hours_parts(
    setting: ActivityScheduleSetting,
) -> tuple[int, int, int]:
    try:
        start, end = active_hours.active_hours_minutes(
            setting.active_hours_start,
            setting.active_hours_end,
        )
    except ValueError:
        start, end = active_hours.active_hours_minutes(
            active_hours.DEFAULT_ACTIVE_HOURS_START,
            active_hours.DEFAULT_ACTIVE_HOURS_END,
        )
    duration = active_hours.active_hours_duration_from_minutes(start, end)
    return start, end, duration


def _local_datetime_for_minute(
    base_date: date,
    minute: int,
    *,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> datetime:
    day_offset, minute_of_day = divmod(minute, 24 * 60)
    hour, local_minute = divmod(minute_of_day, 60)
    return datetime.combine(
        base_date + timedelta(days=day_offset),
        time(hour, local_minute),
        tzinfo=timezone,
    )


def _deterministic_spread_seconds(
    character_id: str,
    reason: str,
    bucket: str,
    max_seconds: int,
) -> int:
    if max_seconds <= 0:
        return 0
    payload = f"{character_id}:{reason}:{bucket}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big") % (max_seconds + 1)
