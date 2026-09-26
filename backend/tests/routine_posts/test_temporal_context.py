"""Routine generation time evidence follows the existing World-local policy."""
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domains.routine_posts.service.temporal_context import build_temporal_context, world_local_iso
from app.domains.routines.policies.planning import daypart_windows


def _input(*, reference: datetime, timezone: str = "Asia/Seoul", day: date = date(2026, 9, 26),
           daypart: str = "morning", plan_timezone: str | None = None,
           persisted_naive: bool = False) -> dict[str, object]:
    start, end = daypart_windows(day, plan_timezone or timezone)[daypart]
    if persisted_naive:
        start, end = start.replace(tzinfo=None), end.replace(tzinfo=None)
    return build_temporal_context(as_of_utc=reference, timezone_name=timezone,
        plan_local_date=day, plan_timezone=plan_timezone or timezone,
        activity_daypart=daypart, window_start=start, window_end=end,
        scheduled_tick=start)


def test_morning_generation_uses_world_clock_and_existing_window() -> None:
    result = _input(reference=datetime(2026, 9, 26, 2, 15, tzinfo=UTC))
    assert result == {
        "version": 1,
        "as_of_utc": "2026-09-26T02:15:00+00:00",
        "timezone": "Asia/Seoul",
        "local_datetime": "2026-09-26T11:15:00+09:00",
        "local_date": "2026-09-26",
        "current_daypart": "morning",
        "activity_window": {
            "plan_local_date": "2026-09-26", "plan_timezone": "Asia/Seoul",
            "daypart": "morning", "starts_at_local": "2026-09-26T06:00:00+09:00",
            "ends_at_local": "2026-09-26T12:00:00+09:00",
            "scheduled_tick_local": "2026-09-26T06:00:00+09:00",
            "contains_reference_time": True,
        },
    }


@pytest.mark.parametrize("hour,minute,second,daypart,within", [
    (5, 59, 59, "dawn", False), (6, 0, 0, "morning", True),
    (11, 59, 59, "morning", True), (12, 0, 0, "afternoon", False),
])
def test_window_is_start_inclusive_and_end_exclusive(
    hour: int, minute: int, second: int, daypart: str, within: bool,
) -> None:
    local = datetime(2026, 9, 26, hour, minute, second, tzinfo=ZoneInfo("Asia/Seoul"))
    result = _input(reference=local.astimezone(UTC))
    assert result["current_daypart"] == daypart
    assert result["activity_window"]["contains_reference_time"] is within


@pytest.mark.parametrize("day,elapsed", [
    (date(2026, 3, 8), timedelta(hours=5)),
    (date(2026, 11, 1), timedelta(hours=7)),
])
def test_daylight_saving_uses_existing_daypart_boundaries(day: date, elapsed: timedelta) -> None:
    start, end = daypart_windows(day, "America/New_York")["dawn"]
    assert end - start == elapsed
    result = _input(reference=start + timedelta(hours=1), timezone="America/New_York",
        day=day, daypart="dawn", persisted_naive=True)
    assert result["activity_window"]["contains_reference_time"] is True
    assert datetime.fromisoformat(result["activity_window"]["starts_at_local"]).astimezone(UTC) == start
    assert datetime.fromisoformat(result["activity_window"]["ends_at_local"]).astimezone(UTC) == end


def test_current_world_date_and_plan_timezone_remain_distinct() -> None:
    reference = datetime(2026, 9, 25, 23, 55, tzinfo=UTC)
    result = _input(reference=reference, timezone="Asia/Seoul",
        day=date(2026, 9, 25), plan_timezone="UTC")
    assert result["local_date"] == "2026-09-26"
    assert result["current_daypart"] == "morning"
    assert result["activity_window"]["plan_local_date"] == "2026-09-25"
    assert result["activity_window"]["plan_timezone"] == "UTC"
    assert result["activity_window"]["contains_reference_time"] is False


def test_persisted_utc_naive_instants_are_normalized_but_reference_must_be_aware() -> None:
    reference = datetime(2026, 9, 26, 2, 15, tzinfo=UTC)
    assert _input(reference=reference, persisted_naive=True) == _input(reference=reference)
    assert world_local_iso(datetime(2026, 9, 26, 0, 48), "Asia/Seoul") == "2026-09-26T09:48:00+09:00"
    with pytest.raises(ValueError, match="routine_reference_time_requires_timezone"):
        _input(reference=datetime(2026, 9, 26, 2, 15))
