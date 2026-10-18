"""Bounded slot command; caller owns the writer transaction and commit/rollback."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session
from app.contracts.environment import EnvironmentSnapshot
from app.domains.routines.constants import SLOT_STATUS_ASSIGNED_IDLE
from app.domains.routines.models import AgentSlot
from app.domains.routines.service.tick_schedule import (
    ActivityScheduleSetting, TickSchedule, aware_utc, initial_tick_schedule, tick_interval_seconds,
)


CADENCE_WAIT_REASONS = ("world_active_hours_waiting", "world_autonomy_disabled")


def changed_schedule(setting: ActivityScheduleSetting, *, character_id: str,
                     now: datetime, last_run_at: datetime | None, timezone: ZoneInfo) -> TickSchedule:
    lower = aware_utc(now)
    if last_run_at is not None:
        lower = max(lower, aware_utc(last_run_at) + timedelta(seconds=tick_interval_seconds(setting)))
    # initial(), not next(), because the elapsed interval is already in lower.
    return initial_tick_schedule(setting, character_id=character_id, now=lower, timezone=timezone)


def refresh_idle_schedule(db: Session, *, owner_id: str, character_id: str,
                          setting: ActivityScheduleSetting, environment: EnvironmentSnapshot,
                          now: datetime) -> str:
    slot = db.scalar(select(AgentSlot).where(AgentSlot.assigned_user_id == owner_id,
        AgentSlot.assigned_character_id == character_id).execution_options(populate_existing=True))
    if slot is None:
        return "no_assignment"
    if slot.locked_by_run_id is not None or slot.lease_expires_at is not None or slot.status == "running":
        return "running_preserved"
    if slot.status != SLOT_STATUS_ASSIGNED_IDLE or (
        slot.last_error is not None and slot.last_error not in CADENCE_WAIT_REASONS
    ):
        return "retry_preserved"
    schedule = changed_schedule(setting, character_id=character_id, now=now,
        last_run_at=slot.last_run_at, timezone=ZoneInfo(environment.timezone))
    if (slot.next_tick_at is not None and aware_utc(slot.next_tick_at) == schedule.next_tick_at
        and slot.heartbeat_interval_seconds == schedule.target_interval_seconds
        and slot.timezone_revision == environment.timezone_revision and slot.last_error is None):
        return "unchanged"
    updated = db.execute(update(AgentSlot).where(
        AgentSlot.agent_id == slot.agent_id, AgentSlot.assigned_user_id == owner_id,
        AgentSlot.assigned_character_id == character_id, AgentSlot.status == SLOT_STATUS_ASSIGNED_IDLE,
        AgentSlot.locked_by_run_id.is_(None), AgentSlot.lease_expires_at.is_(None),
        or_(AgentSlot.last_error.is_(None), AgentSlot.last_error.in_(CADENCE_WAIT_REASONS)),
    ).values(next_tick_at=schedule.next_tick_at, heartbeat_interval_seconds=schedule.target_interval_seconds,
        timezone_revision=environment.timezone_revision, last_error=None).execution_options(synchronize_session="fetch"))
    if updated.rowcount != 1:
        # Caller holds the admission writer. A mismatch is not a successful no-op.
        raise RuntimeError("activity_schedule_assignment_changed")
    return "updated"
