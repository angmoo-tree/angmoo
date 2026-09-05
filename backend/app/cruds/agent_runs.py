from app.domains.routines.service.slot_state import _clear_resident_slot
from app.domains.routines.service.slot_pool import ensure_agent_slots
from app.domains.routines.repository.slots import has_active_resident_slot_run
from app.domains.routines.constants import (LAST_ERROR_MAX_LENGTH, SLOT_STATUS_EMPTY, SLOT_STATUS_IDLE, SLOT_STATUS_BUSY, SLOT_STATUS_ASSIGNED_IDLE, SLOT_STATUS_RUNNING, SLOT_STATUS_COOLDOWN, SLOT_STATUS_UNHEALTHY, FREE_SLOT_STATUSES, DUE_SLOT_STATUSES, ORPHANED_RESIDENT_RUN_ERROR, TEMPORARY_MANUAL_SLOT_RELEASED_ERROR)
from app.domains.routines.constants import ACTIVE_RUN_STATUSES
from app.domains.routines.exceptions import AgentRunConflictError
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.core import unit_of_work


RELATIONSHIP_POINT_KINDS = {"mention_received", "reply_received"}
RELATIONSHIP_POINT_PENDING = "pending"
RELATIONSHIP_POINT_SELECTED = "selected"
RELATIONSHIP_POINT_CONSUMED = "consumed"
RELATIONSHIP_POINT_EXPIRED = "expired"
RELATIONSHIP_POINT_FAILED = "failed"
RELATIONSHIP_POINT_ACTIVE_STATUSES = {
    RELATIONSHIP_POINT_PENDING,
    RELATIONSHIP_POINT_SELECTED,
}


def get_credential(db: Session, credential_id: str) -> models.LlmCredential | None:
    return db.get(models.LlmCredential, credential_id)


def get_default_credential(
    db: Session, owner_id: str, character_id: str | None = None
) -> models.LlmCredential | None:
    query = select(models.LlmCredential).where(
        models.LlmCredential.owner_id == owner_id,
        models.LlmCredential.enabled.is_(True),
    )
    if character_id is not None:
        query = query.where(models.LlmCredential.character_id == character_id)
    return db.scalar(
        query.order_by(models.LlmCredential.created_at.asc(), models.LlmCredential.id.asc())
    )


def relationship_point_pair_key(
    source_character_id: str, recipient_character_id: str
) -> str:
    left, right = sorted([source_character_id, recipient_character_id])
    return f"{left}:{right}"


def relationship_point_source_signature(
    *,
    kind: str,
    recipient_character_id: str,
    source_character_id: str,
    source_post_id: str,
) -> str:
    return "|".join(
        [
            kind,
            recipient_character_id,
            source_character_id,
            source_post_id,
        ]
    )


def relationship_point_chain_id(
    *, source_post_id: str, recipient_character_id: str
) -> str:
    return (
        "rel:"
        + hashlib.sha256(
            f"{source_post_id}:{recipient_character_id}".encode("utf-8")
        ).hexdigest()[:24]
    )


def _relationship_point_payload(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return dict(value)


def create_relationship_point(
    db: Session,
    *,
    kind: str,
    recipient_character_id: str,
    source_character_id: str,
    source_post_id: str,
    source_run_id: str | None = None,
    topic_brief: str = "",
    chain_id: str | None = None,
    chain_depth: int = 0,
    expires_at: datetime,
    payload: dict[str, Any] | None = None,
) -> tuple[models.AgentRelationshipPoint | None, str | None]:
    if kind not in RELATIONSHIP_POINT_KINDS:
        return None, "invalid_kind"
    if not recipient_character_id or not source_character_id or not source_post_id:
        return None, "missing_required_field"
    if recipient_character_id == source_character_id:
        return None, "self_relationship_point"
    source_signature = relationship_point_source_signature(
        kind=kind,
        recipient_character_id=recipient_character_id,
        source_character_id=source_character_id,
        source_post_id=source_post_id,
    )
    existing = db.scalar(
        select(models.AgentRelationshipPoint).where(
            models.AgentRelationshipPoint.source_signature == source_signature
        )
    )
    if existing is not None:
        return existing, "duplicate"
    point = models.AgentRelationshipPoint(
        kind=kind,
        recipient_character_id=recipient_character_id,
        source_character_id=source_character_id,
        source_post_id=source_post_id,
        source_run_id=source_run_id,
        topic_brief=topic_brief[:2000],
        source_signature=source_signature,
        chain_id=chain_id
        or relationship_point_chain_id(
            source_post_id=source_post_id,
            recipient_character_id=recipient_character_id,
        ),
        chain_depth=max(0, int(chain_depth)),
        pair_key=relationship_point_pair_key(
            source_character_id, recipient_character_id
        ),
        status=RELATIONSHIP_POINT_PENDING,
        expires_at=expires_at,
        payload=_relationship_point_payload(payload),
    )
    db.add(point)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(models.AgentRelationshipPoint).where(
                models.AgentRelationshipPoint.source_signature == source_signature
            )
        )
        return existing, "duplicate"
    db.refresh(point)
    return point, None


def count_relationship_points_for_pair_since(
    db: Session, *, pair_key: str, since: datetime
) -> int:
    return (
        db.scalar(
            select(func.count(models.AgentRelationshipPoint.id)).where(
                models.AgentRelationshipPoint.pair_key == pair_key,
                models.AgentRelationshipPoint.created_at >= since,
            )
        )
        or 0
    )


def expire_relationship_points(db: Session, *, now: datetime) -> int:
    points = list(
        db.scalars(
            select(models.AgentRelationshipPoint).where(
                models.AgentRelationshipPoint.status.in_(
                    RELATIONSHIP_POINT_ACTIVE_STATUSES
                ),
                models.AgentRelationshipPoint.expires_at <= now,
            )
        )
    )
    for point in points:
        point.status = RELATIONSHIP_POINT_EXPIRED
        point.failure_class = point.failure_class or "expired"
    if points:
        db.commit()
    return len(points)


def list_pending_relationship_points(
    db: Session,
    *,
    recipient_character_id: str,
    now: datetime,
    limit: int = 10,
) -> list[models.AgentRelationshipPoint]:
    expire_relationship_points(db, now=now)
    return list(
        db.scalars(
            select(models.AgentRelationshipPoint)
            .where(
                models.AgentRelationshipPoint.recipient_character_id
                == recipient_character_id,
                models.AgentRelationshipPoint.status == RELATIONSHIP_POINT_PENDING,
                models.AgentRelationshipPoint.expires_at > now,
            )
            .order_by(
                models.AgentRelationshipPoint.created_at.asc(),
                models.AgentRelationshipPoint.id.asc(),
            )
            .limit(limit)
        )
    )


def mark_relationship_point_selected(
    db: Session,
    point: models.AgentRelationshipPoint,
    *,
    run_id: str,
    now: datetime,
) -> models.AgentRelationshipPoint:
    point.status = RELATIONSHIP_POINT_SELECTED
    point.selected_run_id = run_id
    point.selected_at = now
    db.commit()
    db.refresh(point)
    return point


def release_relationship_point_selection(
    db: Session,
    point: models.AgentRelationshipPoint,
    *,
    failure_class: str | None = None,
) -> models.AgentRelationshipPoint:
    point.status = RELATIONSHIP_POINT_PENDING
    point.selected_run_id = None
    point.selected_at = None
    point.failure_class = failure_class
    db.commit()
    db.refresh(point)
    return point


def mark_relationship_point_consumed(
    db: Session,
    point: models.AgentRelationshipPoint,
    *,
    run_id: str,
    post_id: str,
    now: datetime,
) -> models.AgentRelationshipPoint:
    point.status = RELATIONSHIP_POINT_CONSUMED
    point.consumed_run_id = run_id
    point.consumed_post_id = post_id
    point.consumed_at = now
    db.commit()
    db.refresh(point)
    return point


def mark_relationship_point_replied(
    db: Session,
    point: models.AgentRelationshipPoint,
    *,
    reply_run_id: str,
    reply_post_id: str,
    now: datetime,
) -> models.AgentRelationshipPoint:
    point.reply_run_id = reply_run_id
    point.reply_post_id = reply_post_id
    point.replied_at = now
    db.commit()
    db.refresh(point)
    return point


def mark_relationship_point_failed(
    db: Session,
    point: models.AgentRelationshipPoint,
    *,
    failure_class: str,
) -> models.AgentRelationshipPoint:
    point.status = RELATIONSHIP_POINT_FAILED
    point.failure_class = failure_class
    db.commit()
    db.refresh(point)
    return point


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
    unique_agent_ids = list(
        dict.fromkeys(agent_id for agent_id in agent_ids if agent_id)
    )
    if not unique_agent_ids:
        return None

    ensure_agent_slots(db, unique_agent_ids, commit=commit)

    locked_character_id = db.scalar(
        select(models.Character.id)
        .where(models.Character.id == character_id)
        .with_for_update()
    )
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
) -> models.AgentSlot | None:
    """Atomically claim an unassigned slot for one explicit manual run."""

    unique_agent_ids = list(
        dict.fromkeys(agent_id for agent_id in agent_ids if agent_id)
    )
    if not unique_agent_ids:
        return None

    ensure_agent_slots(db, unique_agent_ids)
    now = datetime.now(UTC)
    locked_character_id = db.scalar(
        select(models.Character.id)
        .where(models.Character.id == character_id)
        .with_for_update()
    )
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


def claim_resident_slot_assignment(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    lease_seconds: int,
) -> models.AgentSlot | None:
    now = datetime.now(UTC)
    owner_controlled = select(models.WorldCharacter.id).where(
        models.WorldCharacter.character_id == models.AgentSlot.assigned_character_id,
        models.WorldCharacter.control_mode == "owner_controlled",
        models.WorldCharacter.status == "active",
    ).exists()
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
    owner_controlled = select(models.WorldCharacter.id).where(
        models.WorldCharacter.character_id == models.AgentSlot.assigned_character_id,
        models.WorldCharacter.control_mode == "owner_controlled",
        models.WorldCharacter.status == "active",
    ).exists()
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
            db.get(models.Character, slot.assigned_character_id)
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
