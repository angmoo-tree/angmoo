from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import ACTIVE_RUN_STATUSES, LAST_ERROR_MAX_LENGTH, ORPHANED_RESIDENT_RUN_ERROR, SLOT_STATUS_ASSIGNED_IDLE, SLOT_STATUS_RUNNING
from app.domains.routines.service import tick_schedule as agent_activity_schedule
from app.domains.routines.service.slot_state import _clear_resident_slot


def recover_expired_resident_slot_runs(
    db: Session,
    *,
    now: datetime,
    next_tick_at_factory: Callable[[models.AgentSlot, datetime], datetime] | None = None,
) -> int:
    now = agent_activity_schedule.aware_utc(now)
    slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(
                models.AgentSlot.status == SLOT_STATUS_RUNNING,
                models.AgentSlot.assigned_user_id.is_not(None),
                models.AgentSlot.assigned_character_id.is_not(None),
                models.AgentSlot.assigned_credential_id.is_not(None),
                models.AgentSlot.locked_by_run_id.is_not(None),
                models.AgentSlot.lease_expires_at.is_not(None),
                models.AgentSlot.lease_expires_at <= now,
            )
            .order_by(
                models.AgentSlot.lease_expires_at.asc(),
                models.AgentSlot.agent_id.asc(),
            )
            .with_for_update(skip_locked=True)
        )
    )
    recovered_count = 0
    for slot in slots:
        locked_run_id = slot.locked_by_run_id or ""
        lease_expires_at = slot.lease_expires_at
        if locked_run_id and not locked_run_id.startswith("pending:"):
            run = db.get(models.AgentRun, locked_run_id)
            if run is not None and run.status in ACTIVE_RUN_STATUSES:
                run.status = "failed"
                run.completed_at = now
                if run.gateway_result is None:
                    run.gateway_result = {
                        "status": "failed",
                        "reason": ORPHANED_RESIDENT_RUN_ERROR,
                        "recovered_at": now.isoformat(),
                        "lease_expires_at": lease_expires_at.isoformat()
                        if lease_expires_at is not None
                        else None,
                    }
        setting = (
            db.get(models.AgentActivitySetting, slot.assigned_character_id)
            if slot.assigned_character_id is not None
            else None
        )
        if setting is None or not setting.auto_enabled:
            # A run-now lease must not become a persistent assignment after a
            # process crash. Its AgentRun evidence (when present) was closed
            # above, so the exact slot can now return to the free pool.
            _clear_resident_slot(slot)
            recovered_count += 1
            continue
        slot.status = SLOT_STATUS_ASSIGNED_IDLE
        slot.locked_by_run_id = None
        slot.lease_expires_at = None
        if (
            slot.next_tick_at is None
            or agent_activity_schedule.aware_utc(slot.next_tick_at) <= now
        ):
            slot.next_tick_at = (
                next_tick_at_factory(slot, now)
                if next_tick_at_factory is not None
                else now
            )
        slot.last_error = (
            f"{ORPHANED_RESIDENT_RUN_ERROR}: run_id={locked_run_id or 'unknown'}"
        )[:LAST_ERROR_MAX_LENGTH]
        recovered_count += 1
    if recovered_count:
        db.commit()
    return recovered_count
