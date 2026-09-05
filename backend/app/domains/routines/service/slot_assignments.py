from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import ACTIVE_RUN_STATUSES, SLOT_STATUS_RUNNING, TEMPORARY_MANUAL_SLOT_RELEASED_ERROR
from app.domains.routines.service.slot_state import _clear_resident_slot


def release_temporary_resident_slot_assignment(
    db: Session,
    *,
    agent_id: str,
    user_id: str,
    character_id: str,
    credential_id: str,
) -> models.AgentSlot | None:
    """Return an exact manual lease to the pool without disabling autonomy."""

    slot = db.scalar(
        select(models.AgentSlot)
        .where(models.AgentSlot.agent_id == agent_id)
        .with_for_update()
    )
    if (
        slot is None
        or slot.assigned_user_id != user_id
        or slot.assigned_character_id != character_id
        or slot.assigned_credential_id != credential_id
    ):
        db.rollback()
        return None

    setting = db.get(models.AgentActivitySetting, character_id)
    if setting is not None and setting.auto_enabled:
        # A concurrent explicit activation adopted this assignment. It is no
        # longer temporary and must remain scheduled.
        db.rollback()
        return slot

    locked_run_id = slot.locked_by_run_id or ""
    if slot.status == SLOT_STATUS_RUNNING and locked_run_id:
        if not locked_run_id.startswith("pending:temporary:"):
            run = db.get(models.AgentRun, locked_run_id)
            if run is not None and run.status in ACTIVE_RUN_STATUSES:
                now = datetime.now(UTC)
                run.status = "failed"
                run.completed_at = now
                if run.gateway_result is None:
                    run.gateway_result = {
                        "status": "failed",
                        "reason": TEMPORARY_MANUAL_SLOT_RELEASED_ERROR,
                        "released_at": now.isoformat(),
                    }
    _clear_resident_slot(slot)
    db.commit()
    db.refresh(slot)
    return slot


def release_resident_slot_assignment(
    db: Session, *, user_id: str, character_id: str, commit: bool = True
) -> models.AgentSlot | None:
    slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(
                models.AgentSlot.assigned_user_id == user_id,
                models.AgentSlot.assigned_character_id == character_id,
            )
            .order_by(
                (models.AgentSlot.status == SLOT_STATUS_RUNNING).desc(),
                models.AgentSlot.last_run_at.desc().nullslast(),
                models.AgentSlot.updated_at.desc(),
                models.AgentSlot.agent_id.asc(),
            )
            .with_for_update(skip_locked=True)
        )
    )
    if not slots:
        return None
    running_slot = next(
        (slot for slot in slots if slot.status == SLOT_STATUS_RUNNING), None
    )
    if running_slot is not None:
        db.rollback()
        return running_slot
    for slot in slots:
        _clear_resident_slot(slot)
    if commit:
        db.commit()
        db.refresh(slots[0])
    else:
        db.flush()
    return slots[0]
