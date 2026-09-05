"""Original KST reference and aware-time rules used by resident decisions."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.domains.routines.constants import APP_TIMEZONE
from app.domains.routines.contracts.planning_context import ResidentClockContext

_KOREAN_WEEKDAYS = (
    "월요일",
    "화요일",
    "수요일",
    "목요일",
    "금요일",
    "토요일",
    "일요일",
)


def _current_kst_date(ctx: ResidentClockContext) -> date:
    return ctx.run_started_at.astimezone(APP_TIMEZONE).date()


def _event_kst_date(event: Any) -> date | None:
    provided_at = _aware_datetime(getattr(event, "provided_at", None))
    if provided_at is None:
        return None
    return provided_at.astimezone(APP_TIMEZONE).date()


def _korean_daypart_label(value: datetime) -> str:
    minute_of_day = value.hour * 60 + value.minute
    if minute_of_day < 5 * 60:
        return "새벽"
    if minute_of_day < 9 * 60:
        return "아침"
    if minute_of_day < 11 * 60 + 30:
        return "오전"
    if minute_of_day < 13 * 60 + 30:
        return "점심"
    if minute_of_day < 17 * 60 + 30:
        return "오후"
    if minute_of_day < 21 * 60:
        return "저녁"
    return "밤"


def _format_current_time_reference(value: datetime) -> str:
    current = value.astimezone(APP_TIMEZONE)
    weekday = _KOREAN_WEEKDAYS[current.weekday()]
    daypart = _korean_daypart_label(current)
    return (
        f"{current.year}년 {current.month}월 {current.day}일 "
        f"{weekday} {daypart} {current.hour:02d}:{current.minute:02d} KST"
    )


def _aware_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _today_kst_window(ctx: ResidentClockContext) -> tuple[datetime, datetime]:
    current_kst = ctx.run_started_at.astimezone(APP_TIMEZONE)
    start_kst = datetime.combine(
        current_kst.date(),
        datetime.min.time(),
        tzinfo=APP_TIMEZONE,
    )
    return start_kst.astimezone(UTC), ctx.run_started_at.astimezone(UTC)


def _yesterday_kst_window(ctx: ResidentClockContext) -> tuple[datetime, datetime]:
    current_kst = ctx.run_started_at.astimezone(APP_TIMEZONE)
    yesterday = current_kst.date() - timedelta(days=1)
    start_kst = datetime.combine(
        yesterday,
        datetime.min.time(),
        tzinfo=APP_TIMEZONE,
    )
    end_kst = start_kst + timedelta(days=1)
    return start_kst.astimezone(UTC), end_kst.astimezone(UTC)
