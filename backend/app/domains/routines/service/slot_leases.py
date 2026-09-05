from __future__ import annotations

from datetime import datetime, UTC, timedelta

from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import LAST_ERROR_MAX_LENGTH, SLOT_STATUS_ASSIGNED_IDLE, SLOT_STATUS_RUNNING


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
) -> None:
    slot = db.get(models.AgentSlot, agent_id)
    if slot is None or slot.locked_by_run_id != run_id:
        return
    now = datetime.now(UTC)
    slot.status = SLOT_STATUS_ASSIGNED_IDLE
    slot.locked_by_run_id = None
    slot.lease_expires_at = None
    slot.last_run_at = now
    slot.next_tick_at = next_tick_at or now + timedelta(seconds=heartbeat_interval_seconds)
    slot.last_error = last_error[:LAST_ERROR_MAX_LENGTH] if last_error else None
    db.commit()
