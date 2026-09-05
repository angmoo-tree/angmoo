from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import SLOT_STATUS_RUNNING


def list_agent_slots(db: Session) -> list[models.AgentSlot]:
    return list(
        db.scalars(select(models.AgentSlot).order_by(models.AgentSlot.agent_id.asc()))
    )


def has_active_resident_slot_run(db: Session, *, now: datetime) -> bool:
    return (
        db.scalar(
            select(models.AgentSlot.agent_id)
            .where(
                models.AgentSlot.status == SLOT_STATUS_RUNNING,
                models.AgentSlot.assigned_user_id.is_not(None),
                models.AgentSlot.assigned_character_id.is_not(None),
                models.AgentSlot.lease_expires_at > now,
            )
            .limit(1)
        )
        is not None
    )


def get_assigned_slot(
    db: Session, character_id: str
) -> models.AgentSlot | None:
    return db.scalar(
        select(models.AgentSlot)
        .where(models.AgentSlot.assigned_character_id == character_id)
        .order_by(
            (models.AgentSlot.status == "running").desc(),
            models.AgentSlot.last_run_at.desc().nullslast(),
            models.AgentSlot.updated_at.desc(),
            models.AgentSlot.agent_id.asc(),
        )
    )
