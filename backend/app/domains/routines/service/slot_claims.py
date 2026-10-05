from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import DUE_SLOT_STATUSES, SLOT_STATUS_RUNNING
from app.domains.routines.contracts.slots import SlotReferences
from app.domains.routines.repository.slots import has_active_resident_slot_run
from app.domains.identity.service.environment import lock_environment_admission
from app.domains.routines.exceptions import ActivityRuntimeValidationError
from app.domains.routines.service.tick_schedule import is_within_active_hours, initial_tick_schedule


def claim_resident_slot_assignment(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    lease_seconds: int,
    references: SlotReferences,
) -> models.AgentSlot | None:
    lock_environment_admission(db, user_id)
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
    slot.admission_metadata = references.capture_activity_input(character_id)

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
    if max_count <= 0 or (allowed_character_ids is not None and not allowed_character_ids):
        return []
    from app.domains.routines.service.environment_schedule import reconcile_environment_schedules
    from app.domains.identity.service.environment import installation_snapshot, lock_environment_admission
    lock_environment_admission(db)
    reconcile_environment_schedules(db, now=now, limit=max(3, max_count * 3),
        settings_reader=lambda setting, character_id: references.effective_settings_for_input(setting,
            references.capture_activity_input(character_id), character_id=character_id))
    environment_revision = installation_snapshot(db).timezone_revision
    if single_flight and has_active_resident_slot_run(db, now=now):
        return []

    conditions = [
        models.AgentSlot.status.in_(DUE_SLOT_STATUSES),
        models.AgentSlot.assigned_user_id.is_not(None),
        models.AgentSlot.assigned_character_id.is_not(None),
        models.AgentSlot.assigned_credential_id.is_not(None),
        models.AgentSlot.next_tick_at <= now,
        models.AgentSlot.timezone_revision == environment_revision,
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
        try:
            metadata = references.capture_activity_input(slot.assigned_character_id)
            configuration = references.activity_configuration_for_input(metadata, character_id=slot.assigned_character_id)
        except ActivityRuntimeValidationError as exc:
            slot.last_error = exc.reason_code
            continue
        if configuration is not None and not configuration.autonomous_enabled:
            slot.last_error = "world_autonomy_disabled"
            continue
        if configuration is not None and not is_within_active_hours(configuration.settings, now,
                timezone=references.activity_timezone(slot.assigned_character_id)):
            slot.next_tick_at = initial_tick_schedule(configuration.settings,
                character_id=slot.assigned_character_id, now=now,
                timezone=references.activity_timezone(slot.assigned_character_id)).next_tick_at
            slot.last_error = "world_active_hours_waiting"
            continue
        assignment_key = (slot.assigned_user_id, slot.assigned_character_id)
        if assignment_key in seen_assignments:
            continue
        seen_assignments.add(assignment_key)
        slot.admission_metadata = metadata
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
