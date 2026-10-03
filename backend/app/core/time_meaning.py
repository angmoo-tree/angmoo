"""Closed civil-time meaning; input language never owns UTC bounds."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.calendar import day_bounds, wall_time


def resolve_calendar_meaning(now: datetime, timezone: str, *, unit: str, offset: int = 0, period: str | None = None):
    if type(offset) is not int or not -366 <= offset <= 0:
        raise ValueError("time_offset_invalid")
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()
    if unit == "day":
        day = today + timedelta(days=offset)
        if period == "morning":
            return wall_time(day, 0, 0, timezone), wall_time(day, 12, 0, timezone)
        if period is not None:
            raise ValueError("time_period_invalid")
        return day_bounds(day, timezone)
    if period is not None:
        raise ValueError("time_period_invalid")
    if unit == "week":
        start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        end = start + timedelta(days=7)
    elif unit == "month":
        ordinal = today.year * 12 + today.month - 1 + offset
        year, month = divmod(ordinal, 12)
        start = date(year, month + 1, 1)
        next_year, next_month = divmod(ordinal + 1, 12)
        end = date(next_year, next_month + 1, 1)
    else:
        raise ValueError("time_unit_invalid")
    return day_bounds(start, timezone)[0], day_bounds(end, timezone)[0]


# Bounded compatibility for old envelopes; new Router output is typed.
LEGACY_CALENDAR_MEANINGS = {
    "today": ("day", 0, None), "오늘": ("day", 0, None), "今日": ("day", 0, None), "اليوم": ("day", 0, None),
    "yesterday": ("day", -1, None), "어제": ("day", -1, None), "昨日": ("day", -1, None), "أمس": ("day", -1, None),
    "사흘 전": ("day", -3, None), "three days ago": ("day", -3, None),
    "오늘 아침": ("day", 0, "morning"), "this morning": ("day", 0, "morning"),
    "지난주": ("week", -1, None), "last week": ("week", -1, None), "先週": ("week", -1, None), "الأسبوع الماضي": ("week", -1, None),
    "지난달": ("month", -1, None), "last month": ("month", -1, None), "先月": ("month", -1, None), "الشهر الماضي": ("month", -1, None),
}
