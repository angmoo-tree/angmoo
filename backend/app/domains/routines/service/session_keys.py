from __future__ import annotations

from app.config import settings
from app.domains.routines.constants import APP_TIMEZONE
from datetime import date, datetime, timedelta


def _scratch_session_key(session_key: str, *, lane: str, run_id: str) -> str:
    safe_lane = "".join(ch for ch in lane if ch.isalnum() or ch in {"-", "_"})
    return f"{session_key}:scratch:{safe_lane}:{run_id}"


def _main_run_session_key(session_key: str, *, run_id: str) -> str:
    return f"{session_key}:run-main:{run_id}"


def _tool_auth_key(session_key: str, *, run_id: str) -> str:
    return f"{session_key}:tool-auth:{run_id}"


def _activity_daypart_window(
    now: datetime | None = None,
) -> tuple[str, date, datetime, datetime]:
    current = now.astimezone(APP_TIMEZONE) if now else datetime.now(APP_TIMEZONE)
    day = current.date()
    hour = current.hour
    if 6 <= hour < 14:
        start = current.replace(hour=6, minute=0, second=0, microsecond=0)
        return "morning", day, start, start + timedelta(hours=8)
    if 14 <= hour < 22:
        start = current.replace(hour=14, minute=0, second=0, microsecond=0)
        return "afternoon", day, start, start + timedelta(hours=8)
    if hour >= 22:
        start = current.replace(hour=22, minute=0, second=0, microsecond=0)
        return "night", day, start, start + timedelta(hours=8)
    start = (current - timedelta(days=1)).replace(
        hour=22, minute=0, second=0, microsecond=0
    )
    return "night", start.date(), start, start + timedelta(hours=8)


def _daypart_main_session_key(
    *, agent_id: str, character_id: str, daypart_start_date: date, activity_daypart: str
) -> str:
    return (
        f"agent:{agent_id}:resident-daypart:{character_id}:"
        f"{daypart_start_date.isoformat()}:{activity_daypart}"
    )


def _daypart_persistent_session_allowed(
    *, character_id: str, require_public_action: bool, enforce_activity_policy: bool
) -> bool:
    if not settings.resident_daypart_persistent_session_enabled:
        return False
    if require_public_action or not enforce_activity_policy:
        return False
    return character_id in settings.resident_daypart_persistent_session_character_ids
