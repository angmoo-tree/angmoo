"""Wire slot assignment and claim policy to its same-Session foreign reads."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.service import slot_assignments, slot_claims
from app.runtime.resident.slot_references import SqlAlchemySlotReferences


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
) -> models.AgentSlot | None:
    return slot_assignments.assign_resident_slot(
        db,
        agent_ids=agent_ids,
        user_id=user_id,
        character_id=character_id,
        credential_id=credential_id,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        next_tick_at=next_tick_at,
        commit=commit,
        references=SqlAlchemySlotReferences(db),
    )


def claim_temporary_resident_slot_assignment(
    db: Session,
    *,
    agent_ids: list[str],
    user_id: str,
    character_id: str,
    credential_id: str,
    heartbeat_interval_seconds: int,
    lease_seconds: int,
) -> models.AgentSlot | None:
    return slot_assignments.claim_temporary_resident_slot_assignment(
        db,
        agent_ids=agent_ids,
        user_id=user_id,
        character_id=character_id,
        credential_id=credential_id,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        lease_seconds=lease_seconds,
        references=SqlAlchemySlotReferences(db),
    )


def claim_resident_slot_assignment(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    lease_seconds: int,
) -> models.AgentSlot | None:
    return slot_claims.claim_resident_slot_assignment(
        db,
        user_id=user_id,
        character_id=character_id,
        lease_seconds=lease_seconds,
        references=SqlAlchemySlotReferences(db),
    )


def claim_due_resident_slots(
    db: Session,
    *,
    now: datetime,
    max_count: int,
    lease_seconds: int,
    allowed_character_ids: set[str] | None = None,
    single_flight: bool = False,
) -> list[models.AgentSlot]:
    return slot_claims.claim_due_resident_slots(
        db,
        now=now,
        max_count=max_count,
        lease_seconds=lease_seconds,
        allowed_character_ids=allowed_character_ids,
        single_flight=single_flight,
        references=SqlAlchemySlotReferences(db),
    )
