"""UTC instants, local calendar boundaries and deterministic DST wall times."""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def utc_instant(value: datetime) -> datetime:
    # Supported legacy database datetimes are naive UTC, never local wall time.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def wall_time(day: date, hour: int, minute: int, zone: str) -> datetime:
    tz = ZoneInfo(zone)
    requested = datetime.combine(day, time(hour, minute))
    # Prefer the first occurrence on overlap. On a gap, advance to the first
    # valid minute (including full-day skips); don't guess a fixed offset.
    for offset in range(48 * 60 + 1):
        wall = requested + timedelta(minutes=offset)
        candidates = []
        for fold in (0, 1):
            instant = wall.replace(tzinfo=tz, fold=fold).astimezone(UTC)
            if instant.astimezone(tz).replace(tzinfo=None) == wall:
                candidates.append(instant)
        if candidates:
            return min(candidates)
    raise ValueError("local_wall_time_unresolvable")


def day_bounds(day: date, zone: str) -> tuple[datetime, datetime]:
    return wall_time(day, 0, 0, zone), wall_time(day + timedelta(days=1), 0, 0, zone)


def month_bounds(day: date, zone: str) -> tuple[datetime, datetime]:
    start = day.replace(day=1)
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return wall_time(start, 0, 0, zone), wall_time(end, 0, 0, zone)


def local_period(now: datetime, zone: str, period: str = "day") -> tuple[datetime, datetime]:
    day = utc_instant(now).astimezone(ZoneInfo(zone)).date()
    if period == "day":
        return day_bounds(day, zone)
    if period == "month":
        return month_bounds(day, zone)
    raise ValueError("calendar_period_invalid")
