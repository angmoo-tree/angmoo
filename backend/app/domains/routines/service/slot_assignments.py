from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import (
    ACTIVE_RUN_STATUSES,
    FREE_SLOT_STATUSES,
    SLOT_STATUS_ASSIGNED_IDLE,
    SLOT_STATUS_RUNNING,
    TEMPORARY_MANUAL_SLOT_RELEASED_ERROR,
)
from app.domains.routines.contracts.slots import SlotReferences
from app.domains.routines.service.slot_pool import ensure_agent_slots
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


def assign_resident_slot(
    db: Session,
    *,
    agent_ids: list[str],
    user_id: str,
    character_id: str,
    credential_id: str,
    heartbeat_interval_seconds: int,
    next_tick_at: datetime,
    commit: bool = True,
    references: SlotReferences,
) -> models.AgentSlot | None:
    unique_agent_ids = list(
        dict.fromkeys(agent_id for agent_id in agent_ids if agent_id)
    )
    if not unique_agent_ids:
        return None

    ensure_agent_slots(db, unique_agent_ids, commit=commit)

    locked_character_id = references.lock_character_id(character_id)
    if locked_character_id is None:
        db.rollback()
        return None

    existing_slot = db.scalar(
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
        .with_for_update()
    )
    if existing_slot is not None and existing_slot.status == SLOT_STATUS_RUNNING:
        db.rollback()
        return None

    slot = existing_slot or db.scalar(
        select(models.AgentSlot)
        .where(
            models.AgentSlot.agent_id.in_(unique_agent_ids),
            models.AgentSlot.status.in_(FREE_SLOT_STATUSES),
        )
        .order_by(models.AgentSlot.updated_at.asc(), models.AgentSlot.agent_id.asc())
        .with_for_update(skip_locked=True)
    )
    if slot is None:
        db.rollback()
        return None

    try:
        with db.begin_nested():
            duplicate_slots = list(
                db.scalars(
                    select(models.AgentSlot)
                    .where(
                        models.AgentSlot.assigned_user_id == user_id,
                        models.AgentSlot.assigned_character_id == character_id,
                        models.AgentSlot.agent_id != slot.agent_id,
                        models.AgentSlot.status != SLOT_STATUS_RUNNING,
                    )
                    .with_for_update()
                )
            )
            for duplicate in duplicate_slots:
                _clear_resident_slot(duplicate)

            slot.status = SLOT_STATUS_ASSIGNED_IDLE
            slot.assigned_user_id = user_id
            slot.assigned_character_id = character_id
            slot.assigned_credential_id = credential_id
            slot.heartbeat_interval_seconds = heartbeat_interval_seconds
            slot.next_tick_at = next_tick_at
            slot.locked_by_run_id = None
            slot.lease_expires_at = None
            slot.last_error = None
            db.flush()
    except IntegrityError:
        slot = db.scalar(
            select(models.AgentSlot).where(
                models.AgentSlot.assigned_character_id == character_id
            )
        )
        if slot is None:
            db.rollback()
            return None
    if commit:
        db.commit()
        db.refresh(slot)
    return slot


def claim_temporary_resident_slot_assignment(
    db: Session,
    *,
    agent_ids: list[str],
    user_id: str,
    character_id: str,
    credential_id: str,
    heartbeat_interval_seconds: int,
    lease_seconds: int,
    references: SlotReferences,
) -> models.AgentSlot | None:
    """Atomically claim an unassigned slot for one explicit manual run."""

    unique_agent_ids = list(
        dict.fromkeys(agent_id for agent_id in agent_ids if agent_id)
    )
    if not unique_agent_ids:
        return None

    ensure_agent_slots(db, unique_agent_ids)
    now = datetime.now(UTC)
    locked_character_id = references.lock_character_id(character_id)
    if locked_character_id is None:
        db.rollback()
        return None

    existing_slot = db.scalar(
        select(models.AgentSlot)
        .where(models.AgentSlot.assigned_character_id == character_id)
        .with_for_update()
    )
    if existing_slot is not None:
        db.rollback()
        return None

    slot = db.scalar(
        select(models.AgentSlot)
        .where(
            models.AgentSlot.agent_id.in_(unique_agent_ids),
            models.AgentSlot.status.in_(FREE_SLOT_STATUSES),
            models.AgentSlot.assigned_user_id.is_(None),
            models.AgentSlot.assigned_character_id.is_(None),
            models.AgentSlot.assigned_credential_id.is_(None),
        )
        .order_by(models.AgentSlot.updated_at.asc(), models.AgentSlot.agent_id.asc())
        .with_for_update(skip_locked=True)
    )
    if slot is None:
        db.rollback()
        return None

    claim_material = (
        f"{slot.agent_id}:{user_id}:{character_id}:{credential_id}:{now.isoformat()}"
    )
    claim_token = (
        "pending:temporary:"
        + hashlib.sha256(claim_material.encode("utf-8")).hexdigest()[:32]
    )
    try:
        with db.begin_nested():
            slot.status = SLOT_STATUS_RUNNING
            slot.assigned_user_id = user_id
            slot.assigned_character_id = character_id
            slot.assigned_credential_id = credential_id
            slot.heartbeat_interval_seconds = heartbeat_interval_seconds
            slot.next_tick_at = None
            slot.locked_by_run_id = claim_token
            slot.lease_expires_at = now + timedelta(seconds=lease_seconds)
            slot.last_error = None
            db.flush()
    except IntegrityError:
        db.rollback()
        return None
    db.commit()
    db.refresh(slot)
    return slot
