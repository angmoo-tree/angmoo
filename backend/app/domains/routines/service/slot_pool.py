from __future__ import annotations

from datetime import datetime, UTC, timedelta

from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import FREE_SLOT_STATUSES, LAST_ERROR_MAX_LENGTH, SLOT_STATUS_BUSY, SLOT_STATUS_EMPTY


def ensure_agent_slots(
    db: Session,
    agent_ids: list[str],
    *,
    commit: bool = True,
) -> None:
    unique_agent_ids = list(
        dict.fromkeys(agent_id for agent_id in agent_ids if agent_id)
    )
    if not unique_agent_ids:
        return

    existing = set(
        db.scalars(
            select(models.AgentSlot.agent_id).where(
                models.AgentSlot.agent_id.in_(unique_agent_ids)
            )
        )
    )
    missing = [
        models.AgentSlot(agent_id=agent_id, status=SLOT_STATUS_EMPTY)
        for agent_id in unique_agent_ids
        if agent_id not in existing
    ]
    if not missing:
        return

    db.add_all(missing)
    if not commit:
        db.flush()
        return
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def claim_agent_slot(
    db: Session, *, run_id: str, agent_ids: list[str], lease_seconds: int
) -> models.AgentSlot | None:
    unique_agent_ids = list(
        dict.fromkeys(agent_id for agent_id in agent_ids if agent_id)
    )
    if not unique_agent_ids:
        return None

    ensure_agent_slots(db, unique_agent_ids)

    now = datetime.now(UTC)
    slot = db.scalar(
        select(models.AgentSlot)
        .where(
            models.AgentSlot.agent_id.in_(unique_agent_ids),
            or_(
                models.AgentSlot.status.in_(FREE_SLOT_STATUSES),
                models.AgentSlot.lease_expires_at <= now,
            ),
        )
        .order_by(models.AgentSlot.updated_at.asc(), models.AgentSlot.agent_id.asc())
        .with_for_update(skip_locked=True)
    )
    if slot is None:
        db.rollback()
        return None

    slot.status = SLOT_STATUS_BUSY
    slot.locked_by_run_id = run_id
    slot.lease_expires_at = now + timedelta(seconds=lease_seconds)
    slot.last_error = None
    db.commit()
    db.refresh(slot)
    return slot


def release_agent_slot(
    db: Session,
    *,
    agent_id: str,
    run_id: str,
    last_error: str | None = None,
) -> None:
    slot = db.get(models.AgentSlot, agent_id)
    if slot is None or slot.locked_by_run_id != run_id:
        return

    slot.status = SLOT_STATUS_EMPTY
    slot.locked_by_run_id = None
    slot.lease_expires_at = None
    slot.last_error = last_error[:LAST_ERROR_MAX_LENGTH] if last_error else None
    db.commit()
