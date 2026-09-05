"""Authorize and prepare explicit Resident assignment requests."""
from __future__ import annotations
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.config import settings
from app.domains.routines import models, schemas
from app.domains.routines.contracts.slot_requests import SlotRequestWorkflows
from app.domains.routines.exceptions import AgentSlotUnavailableError
from app.domains.routines.service import activity_settings, tick_schedule, slot_assignments
from app.domains.routines.service.run_identity import _validate_character_and_credential


def assign_resident_slot(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    credential_id: str,
    heartbeat_interval_seconds: int,
    next_tick_at: datetime | None = None,
    commit: bool = True,
    workflows: SlotRequestWorkflows,
) -> schemas.AgentSlotRead:
    workflows.ensure_auto_ticks_available(db)
    _validate_character_and_credential(
        workflows.identity_references(),
        user_id=user_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    candidate_agent_ids = settings.openclaw_agent_ids
    setting = activity_settings.ensure_setting(db, character_id, commit=commit)
    scheduled_tick_at = next_tick_at or tick_schedule.initial_tick_schedule(
        setting,
        character_id=character_id,
        now=datetime.now(UTC),
        timezone=workflows.timezone_reader(
            db, character_id=character_id
        ),
    ).next_tick_at
    slot = slot_assignments.assign_resident_slot(
        db,
        agent_ids=candidate_agent_ids,
        user_id=user_id,
        character_id=character_id,
        credential_id=credential_id,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        next_tick_at=scheduled_tick_at,
        commit=commit,
        references=workflows.slot_references(),
    )
    if slot is None:
        raise AgentSlotUnavailableError(
            "resident_slot_unavailable: No resident slot is available for "
            f"{character_id}; configured_pool={len(candidate_agent_ids)}"
        )
    return schemas.AgentSlotRead.model_validate(slot)


def claim_temporary_resident_slot(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    credential_id: str,
    heartbeat_interval_seconds: int,
    timeout_seconds: int,
    workflows: SlotRequestWorkflows,
) -> models.AgentSlot:
    workflows.ensure_run_now_available(db)
    _validate_character_and_credential(
        workflows.identity_references(),
        user_id=user_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    slot = slot_assignments.claim_temporary_resident_slot_assignment(
        db,
        agent_ids=settings.openclaw_agent_ids,
        user_id=user_id,
        character_id=character_id,
        credential_id=credential_id,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        lease_seconds=timeout_seconds + 90,
        references=workflows.slot_references(),
    )
    if slot is None:
        raise AgentSlotUnavailableError(
            f"No temporary OpenClaw slot is available for character {character_id}"
        )
    return slot
