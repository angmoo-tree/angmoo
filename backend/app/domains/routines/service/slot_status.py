from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.routines import models, schemas
from app.domains.routines.repository import slots as slot_queries
from app.domains.routines.service import tick_schedule as agent_activity_schedule


def list_resident_slots(db: Session) -> list[schemas.AgentSlotRead]:
    return [
        schemas.AgentSlotRead.model_validate(slot)
        for slot in slot_queries.list_agent_slots(db)
    ]


def list_resident_slots_for_user(
    db: Session, user_id: str
) -> list[schemas.AgentSlotPublicRead]:
    return [
        schemas.AgentSlotPublicRead.model_validate(slot)
        for slot in slot_queries.list_agent_slots(db)
        if slot.assigned_user_id == user_id
    ]


def _resident_slot_is_due(slot: models.AgentSlot, *, now: datetime) -> bool:
    if slot.next_tick_at is None:
        return False
    return agent_activity_schedule.aware_utc(
        slot.next_tick_at
    ) <= agent_activity_schedule.aware_utc(now)
