from __future__ import annotations

from datetime import datetime, UTC, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import update

from app.domains.routines import models
from app.domains.routines.constants import LAST_ERROR_MAX_LENGTH, SLOT_STATUS_ASSIGNED_IDLE, SLOT_STATUS_RUNNING
from app.domains.routines.contracts.scheduling import CompletionScheduleResolver


def set_resident_slot_run_id(
    db: Session, *, agent_id: str, run_id: str, lease_seconds: int
) -> models.AgentSlot | None:
    slot = db.get(models.AgentSlot, agent_id)
    if slot is None or slot.status != SLOT_STATUS_RUNNING:
        return None
    slot.locked_by_run_id = run_id
    slot.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    db.commit()
    db.refresh(slot)
    return slot


def extend_resident_slot_lease(
    db: Session, *, agent_id: str, run_id: str, lease_seconds: int
) -> models.AgentSlot | None:
    slot = db.get(models.AgentSlot, agent_id)
    if slot is None or slot.locked_by_run_id != run_id:
        return None
    slot.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    db.commit()
    db.refresh(slot)
    return slot


def complete_resident_slot_run(
    db: Session,
    *,
    agent_id: str,
    run_id: str,
    heartbeat_interval_seconds: int,
    next_tick_at: datetime | None = None,
    last_error: str | None = None,
    schedule_resolver: CompletionScheduleResolver | None = None,
) -> None:
    if schedule_resolver is not None and last_error is None:
        # A conditional write acquires the real SQLite writer before reading
        # current settings. FOR UPDATE alone cannot provide that guarantee.
        owned = db.execute(update(models.AgentSlot).where(
            models.AgentSlot.agent_id == agent_id, models.AgentSlot.locked_by_run_id == run_id,
            models.AgentSlot.status == SLOT_STATUS_RUNNING,
            models.AgentSlot.assigned_user_id == schedule_resolver.owner_id,
            models.AgentSlot.assigned_character_id == schedule_resolver.character_id,
        ).values(updated_at=models.AgentSlot.updated_at).execution_options(synchronize_session=False))
        if owned.rowcount != 1:
            # No commit of caller work on a lost run. Caller closes/rolls back
            # its unit of work, just as on the existing stale-run return below.
            return
        slot = db.get(models.AgentSlot, agent_id, populate_existing=True)
        now = datetime.now(UTC)
        resolved = schedule_resolver.resolve(db, slot, now)
        if resolved is not None:
            next_tick_at = resolved.tick.next_tick_at
            slot.heartbeat_interval_seconds = resolved.tick.target_interval_seconds
            slot.timezone_revision = resolved.timezone_revision
    else:
        slot = db.get(models.AgentSlot, agent_id)
        now = datetime.now(UTC)
    if slot is None or slot.locked_by_run_id != run_id:
        return
    slot.status = SLOT_STATUS_ASSIGNED_IDLE
    slot.locked_by_run_id = None
    slot.lease_expires_at = None
    slot.last_run_at = now
    slot.next_tick_at = next_tick_at or now + timedelta(seconds=heartbeat_interval_seconds)
    slot.last_error = last_error[:LAST_ERROR_MAX_LENGTH] if last_error else None
    db.commit()


def cancel_resident_run(db, *, agent_id, run_id, owner_id, character_id, now, reason, resolve_schedule):
    """One caller-clean, conditional writer; the scheduler before-commit fence remains active."""
    from app.core.sqlite_concurrency import run_sqlite_session_immediate
    from app.domains.routines.constants import ACTIVE_RUN_STATUSES
    if db.in_transaction():
        raise RuntimeError("cancelled_run_requires_clean_session")
    def operation():
        locked = db.execute(update(models.AgentSlot).where(
            models.AgentSlot.agent_id == agent_id, models.AgentSlot.locked_by_run_id == run_id,
            models.AgentSlot.status == SLOT_STATUS_RUNNING, models.AgentSlot.assigned_user_id == owner_id,
            models.AgentSlot.assigned_character_id == character_id,
        ).values(updated_at=models.AgentSlot.updated_at).execution_options(synchronize_session=False))
        if locked.rowcount != 1:
            raise ValueError("cancelled_run_lease_not_owned")
        run = db.get(models.AgentRun, run_id, populate_existing=True)
        slot = db.get(models.AgentSlot, agent_id, populate_existing=True)
        if run is None or run.user_id != owner_id or run.character_id != character_id or run.status not in ACTIVE_RUN_STATUSES:
            raise ValueError("cancelled_run_not_active")
        next_tick = resolve_schedule(db, slot, now)
        run.status, run.completed_at = "cancelled", now
        run.gateway_result = {**(run.gateway_result or {}), "status":"cancelled", "reason":str(reason), "cancelled_at":now.isoformat()}
        slot.status, slot.locked_by_run_id, slot.lease_expires_at = SLOT_STATUS_ASSIGNED_IDLE, None, None
        slot.last_run_at, slot.next_tick_at, slot.last_error = now, next_tick, str(reason)
    return run_sqlite_session_immediate(db, operation, require_clean=True)
