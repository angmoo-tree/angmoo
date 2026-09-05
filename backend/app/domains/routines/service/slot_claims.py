from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import DUE_SLOT_STATUSES, SLOT_STATUS_RUNNING
from app.domains.routines.contracts.slots import SlotReferences
from app.domains.routines.repository.slots import has_active_resident_slot_run


def claim_resident_slot_assignment(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    lease_seconds: int,
    references: SlotReferences,
) -> models.AgentSlot | None:
    now = datetime.now(UTC)
    owner_controlled = references.owner_controlled_predicate()
    slot = db.scalar(
        select(models.AgentSlot)
        .where(
            models.AgentSlot.assigned_user_id == user_id,
            models.AgentSlot.assigned_character_id == character_id,
            or_(
                models.AgentSlot.status.in_(DUE_SLOT_STATUSES),
                models.AgentSlot.lease_expires_at <= now,
            ),
            ~owner_controlled,
        )
        .order_by(models.AgentSlot.updated_at.asc(), models.AgentSlot.agent_id.asc())
        .with_for_update(skip_locked=True)
    )
    if slot is None:
        db.rollback()
        return None

    slot.status = SLOT_STATUS_RUNNING
    slot.locked_by_run_id = f"pending:{slot.agent_id}:{int(now.timestamp())}"
    slot.lease_expires_at = now + timedelta(seconds=lease_seconds)
    slot.last_error = None
    db.commit()
    db.refresh(slot)
    return slot


def claim_due_resident_slots(
    db: Session,
    *,
    now: datetime,
    max_count: int,
    lease_seconds: int,
    allowed_character_ids: set[str] | None = None,
    single_flight: bool = False,
    references: SlotReferences,
) -> list[models.AgentSlot]:
    if allowed_character_ids is not None and not allowed_character_ids:
        return []
    if single_flight and has_active_resident_slot_run(db, now=now):
        return []

    conditions = [
        models.AgentSlot.status.in_(DUE_SLOT_STATUSES),
        models.AgentSlot.assigned_user_id.is_not(None),
        models.AgentSlot.assigned_character_id.is_not(None),
        models.AgentSlot.assigned_credential_id.is_not(None),
        models.AgentSlot.next_tick_at <= now,
    ]
    owner_controlled = references.owner_controlled_predicate()
    conditions.append(~owner_controlled)
    if allowed_character_ids is not None:
        conditions.append(
            models.AgentSlot.assigned_character_id.in_(allowed_character_ids)
        )

    candidate_slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(*conditions)
            .order_by(models.AgentSlot.next_tick_at.asc(), models.AgentSlot.agent_id.asc())
            .limit(max(max_count * 3, max_count))
            .with_for_update(skip_locked=True)
        )
    )
    slots: list[models.AgentSlot] = []
    seen_assignments: set[tuple[str | None, str | None]] = set()
    for slot in candidate_slots:
        character = (
            references.get_character(slot.assigned_character_id)
            if slot.assigned_character_id
            else None
        )
        if (
            character is None
            or character.deleted_at is not None
            or character.moderation_status == "suspended"
        ):
            continue
        assignment_key = (slot.assigned_user_id, slot.assigned_character_id)
        if assignment_key in seen_assignments:
            continue
        seen_assignments.add(assignment_key)
        slots.append(slot)
        if len(slots) >= max_count:
            break
    for slot in slots:
        slot.status = SLOT_STATUS_RUNNING
        slot.locked_by_run_id = f"pending:{slot.agent_id}:{int(now.timestamp())}"
        slot.lease_expires_at = now + timedelta(seconds=lease_seconds)
        slot.last_error = None
    db.commit()
    for slot in slots:
        db.refresh(slot)
    return slots
