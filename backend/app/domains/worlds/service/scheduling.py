"""World timezone-change collaboration in the caller-owned transaction.

This existing query touches resident activity and idle slots atomically with the
World update. It neither starts a worker nor commits; AR-B4 owns the subsequent
activity/scheduler ownership transition.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import agent_activity_schedule


@dataclass(frozen=True, slots=True)
class _WorldAutonomyScheduleSetting:
    activity_interval_minutes: int
    active_hours_start: str
    active_hours_end: str

def reschedule_world_autonomy_slots(
    db: Session,
    *,
    world_id: str,
    timezone_name: str,
    now: datetime | None = None,
) -> int:
    """Recompute enabled idle slots after the owning World's timezone changes."""

    try:
        activity_timezone = ZoneInfo(timezone_name)
    except (KeyError, ValueError):
        activity_timezone = agent_activity_schedule.APP_TIMEZONE
    current = agent_activity_schedule.aware_utc(now or datetime.now(UTC))
    lock_suffix = " FOR UPDATE" if db.get_bind().dialect.name == "postgresql" else ""
    rows = db.execute(
        text(
            """
            SELECT activity.character_id,
                   activity.activity_interval_minutes,
                   activity.active_hours_start,
                   activity.active_hours_end,
                   slot.agent_id
              FROM agent_activity_settings AS activity
              JOIN world_characters AS resident
                ON resident.character_id = activity.character_id
              JOIN agent_slots AS slot
                ON slot.assigned_character_id = activity.character_id
             WHERE resident.world_id = :world_id
               AND resident.control_mode = 'autonomous'
               AND resident.status = 'active'
               AND resident.autonomous_enabled = true
               AND activity.auto_enabled = true
               AND slot.status = 'assigned_idle'
            """
            + lock_suffix
        ),
        {"world_id": world_id},
    ).mappings()
    changed = 0
    for row in rows:
        setting = _WorldAutonomyScheduleSetting(
            activity_interval_minutes=int(row["activity_interval_minutes"]),
            active_hours_start=str(row["active_hours_start"]),
            active_hours_end=str(row["active_hours_end"]),
        )
        within_active_hours = agent_activity_schedule.is_within_active_hours(
            setting,
            current,
            timezone=activity_timezone,
        )
        schedule = agent_activity_schedule.next_tick_schedule(
            setting,
            character_id=str(row["character_id"]),
            now=current,
            within_active_hours=within_active_hours,
            timezone=activity_timezone,
        )
        db.execute(
            text(
                """
                UPDATE agent_slots
                   SET next_tick_at = :next_tick_at,
                       heartbeat_interval_seconds = :heartbeat_interval_seconds,
                       updated_at = :updated_at
                 WHERE agent_id = :agent_id
                """
            ),
            {
                "agent_id": row["agent_id"],
                "next_tick_at": schedule.next_tick_at,
                "heartbeat_interval_seconds": (
                    agent_activity_schedule.tick_interval_seconds(setting)
                ),
                "updated_at": current,
            },
        )
        changed += 1
    return changed
