"""World-local time evidence for one routine generation decision."""
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.domains.routines.service import aware_utc, daypart_windows


ROUTINE_TEMPORAL_INSTRUCTIONS = (
    "When temporal_context is supplied, its local_datetime and current_daypart are the "
    "authoritative present time. The activity window describes the approved routine, "
    "not a different present clock. Keep the scene plan, post title/body/signature and "
    "proposed state note consistent with that time. Prior posts, results and state notes "
    "may contain stale 'tonight', 'yesterday' or 'tomorrow' language: preserve confirmed "
    "facts, but do not move the present scene to match those phrases. Distinguish current "
    "events from memories and future intentions. 'conclude' closes this scene, not the "
    "whole day or necessarily the episode; it does not imply bedtime or a new date. "
    "Practice can finish, be reviewed or include a rest within its scheduled window. "
    "Do not restart completed scenes. If temporal_context is absent in an older saved "
    "request, use its existing time evidence without inventing a date change."
)


def world_local_iso(value: datetime, timezone_name: str) -> str:
    """Interpret known persisted UTC instants using the World IANA time zone."""
    return aware_utc(value).astimezone(ZoneInfo(timezone_name)).isoformat()


def build_temporal_context(
    *,
    as_of_utc: datetime,
    timezone_name: str,
    plan_local_date: date,
    plan_timezone: str,
    activity_daypart: str,
    window_start: datetime,
    window_end: datetime,
    scheduled_tick: datetime,
) -> dict[str, object]:
    """Use one explicit decision instant; never read the clock or change eligibility."""
    if as_of_utc.tzinfo is None or as_of_utc.utcoffset() is None:
        raise ValueError("routine_reference_time_requires_timezone")
    current = as_of_utc.astimezone(UTC)
    local = current.astimezone(ZoneInfo(timezone_name))
    current_daypart = next(
        (
            daypart
            for daypart, (start, end) in daypart_windows(local.date(), timezone_name).items()
            if start <= current < end
        ),
        None,
    )
    if current_daypart is None:
        raise ValueError("routine_current_daypart_invalid")
    start, end = aware_utc(window_start), aware_utc(window_end)
    return {
        "version": 1,
        "as_of_utc": current.isoformat(),
        "timezone": timezone_name,
        "local_datetime": local.isoformat(),
        "local_date": local.date().isoformat(),
        "current_daypart": current_daypart,
        "activity_window": {
            "plan_local_date": plan_local_date.isoformat(),
            "plan_timezone": plan_timezone,
            "daypart": activity_daypart,
            "starts_at_local": world_local_iso(start, timezone_name),
            "ends_at_local": world_local_iso(end, timezone_name),
            "scheduled_tick_local": world_local_iso(scheduled_tick, timezone_name),
            "contains_reference_time": start <= current < end,
        },
    }
