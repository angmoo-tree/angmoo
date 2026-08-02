import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models


ACTIVE_RUN_STATUSES = {"running"}
LAST_ERROR_MAX_LENGTH = 2000
SLOT_STATUS_EMPTY = "empty"
SLOT_STATUS_IDLE = "idle"
SLOT_STATUS_BUSY = "busy"
SLOT_STATUS_ASSIGNED_IDLE = "assigned_idle"
SLOT_STATUS_RUNNING = "running"
SLOT_STATUS_COOLDOWN = "cooldown"
SLOT_STATUS_UNHEALTHY = "unhealthy"
FREE_SLOT_STATUSES = {SLOT_STATUS_EMPTY, SLOT_STATUS_IDLE}
DUE_SLOT_STATUSES = {SLOT_STATUS_ASSIGNED_IDLE, SLOT_STATUS_COOLDOWN}
ORPHANED_RESIDENT_RUN_ERROR = "resident_run_orphaned_after_expired_lease"
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


class AgentRunConflictError(Exception):
    pass


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


def create_agent_run(
    db: Session,
    *,
    run_id: str,
    user_id: str,
    character_id: str,
    post_id: str | None,
    credential_id: str | None,
    agent_id: str,
    session_key: str,
    tool_auth_key: str | None = None,
) -> models.AgentRun:
    run = models.AgentRun(
        id=run_id,
        user_id=user_id,
        character_id=character_id,
        post_id=post_id,
        credential_id=credential_id,
        agent_id=agent_id,
        session_key=session_key,
        tool_auth_key=tool_auth_key,
        status="running",
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AgentRunConflictError("An active agent run already exists") from exc
    db.refresh(run)
    return run


def mark_agent_run_finished(
    db: Session,
    run_id: str,
    status: str,
    gateway_result: dict[str, Any] | None = None,
) -> None:
    run = db.get(models.AgentRun, run_id)
    if run is None:
        return
    run.status = status
    run.completed_at = datetime.now(UTC)
    if gateway_result is not None:
        run.gateway_result = gateway_result
    db.commit()


def set_agent_run_post_id(db: Session, run_id: str, post_id: str) -> None:
    run = db.get(models.AgentRun, run_id)
    if run is None:
        return
    run.post_id = post_id
    db.commit()


def get_public_action_execution_by_signature(
    db: Session, signature: str
) -> models.AgentPublicActionExecution | None:
    return db.scalar(
        select(models.AgentPublicActionExecution).where(
            models.AgentPublicActionExecution.signature == signature
        )
    )


def create_public_action_execution(
    db: Session,
    *,
    run_id: str,
    character_id: str,
    signature: str,
    scope: str,
    action_type: str,
    target_post_id: str | None = None,
    target_profile_type: str | None = None,
    target_profile_id: str | None = None,
    brief_hash: str | None = None,
) -> models.AgentPublicActionExecution:
    execution = models.AgentPublicActionExecution(
        run_id=run_id,
        character_id=character_id,
        signature=signature,
        scope=scope,
        action_type=action_type,
        target_post_id=target_post_id,
        target_profile_type=target_profile_type,
        target_profile_id=target_profile_id,
        brief_hash=brief_hash,
        status="pending",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def mark_public_action_execution_finished(
    db: Session,
    execution: models.AgentPublicActionExecution,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    failure_class: str | None = None,
) -> models.AgentPublicActionExecution:
    execution.status = status
    execution.result = result
    execution.failure_class = failure_class
    execution.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(execution)
    return execution


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


def get_active_run_for_session(
    db: Session, session_key: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(
            models.AgentRun.session_key == session_key,
            models.AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_active_run_for_tool_auth_key(
    db: Session, tool_auth_key: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(
            models.AgentRun.tool_auth_key == tool_auth_key,
            models.AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_latest_run_for_session(
    db: Session, session_key: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(models.AgentRun.session_key == session_key)
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_latest_run_for_tool_auth_key(
    db: Session, tool_auth_key: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(models.AgentRun.tool_auth_key == tool_auth_key)
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_latest_manual_run_for_user(
    db: Session, user_id: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(
            models.AgentRun.user_id == user_id,
            models.AgentRun.session_key.contains(":resident-manual:"),
        )
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_latest_first_greeting_run_for_user(
    db: Session, user_id: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(
            models.AgentRun.user_id == user_id,
            models.AgentRun.session_key.contains(":first-greeting:"),
        )
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def ensure_agent_slots(db: Session, agent_ids: list[str]) -> None:
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


def list_agent_slots(db: Session) -> list[models.AgentSlot]:
    return list(
        db.scalars(select(models.AgentSlot).order_by(models.AgentSlot.agent_id.asc()))
    )


def recover_expired_resident_slot_runs(
    db: Session,
    *,
    now: datetime,
    next_tick_at_factory: Callable[[models.AgentSlot, datetime], datetime] | None = None,
) -> int:
    slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(
                models.AgentSlot.status == SLOT_STATUS_RUNNING,
                models.AgentSlot.assigned_user_id.is_not(None),
                models.AgentSlot.assigned_character_id.is_not(None),
                models.AgentSlot.assigned_credential_id.is_not(None),
                models.AgentSlot.locked_by_run_id.is_not(None),
                models.AgentSlot.lease_expires_at.is_not(None),
                models.AgentSlot.lease_expires_at <= now,
            )
            .order_by(
                models.AgentSlot.lease_expires_at.asc(),
                models.AgentSlot.agent_id.asc(),
            )
            .with_for_update(skip_locked=True)
        )
    )
    recovered_count = 0
    for slot in slots:
        locked_run_id = slot.locked_by_run_id or ""
        lease_expires_at = slot.lease_expires_at
        if locked_run_id and not locked_run_id.startswith("pending:"):
            run = db.get(models.AgentRun, locked_run_id)
            if run is not None and run.status in ACTIVE_RUN_STATUSES:
                run.status = "failed"
                run.completed_at = now
                if run.gateway_result is None:
                    run.gateway_result = {
                        "status": "failed",
                        "reason": ORPHANED_RESIDENT_RUN_ERROR,
                        "recovered_at": now.isoformat(),
                        "lease_expires_at": lease_expires_at.isoformat()
                        if lease_expires_at is not None
                        else None,
                    }
        slot.status = SLOT_STATUS_ASSIGNED_IDLE
        slot.locked_by_run_id = None
        slot.lease_expires_at = None
        if slot.next_tick_at is None or slot.next_tick_at <= now:
            slot.next_tick_at = (
                next_tick_at_factory(slot, now)
                if next_tick_at_factory is not None
                else now
            )
        slot.last_error = (
            f"{ORPHANED_RESIDENT_RUN_ERROR}: run_id={locked_run_id or 'unknown'}"
        )[:LAST_ERROR_MAX_LENGTH]
        recovered_count += 1
    if recovered_count:
        db.commit()
    return recovered_count


def _clear_resident_slot(slot: models.AgentSlot) -> None:
    slot.status = SLOT_STATUS_EMPTY
    slot.assigned_user_id = None
    slot.assigned_character_id = None
    slot.assigned_credential_id = None
    slot.next_tick_at = None
    slot.last_run_at = None
    slot.heartbeat_interval_seconds = None
    slot.locked_by_run_id = None
    slot.lease_expires_at = None
    slot.last_error = None


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

    ensure_agent_slots(db, unique_agent_ids)

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


def claim_resident_slot_assignment(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    lease_seconds: int,
) -> models.AgentSlot | None:
    now = datetime.now(UTC)
    slot = db.scalar(
        select(models.AgentSlot)
        .where(
            models.AgentSlot.assigned_user_id == user_id,
            models.AgentSlot.assigned_character_id == character_id,
            or_(
                models.AgentSlot.status.in_(DUE_SLOT_STATUSES),
                models.AgentSlot.lease_expires_at <= now,
            ),
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


def set_resident_slot_run_id(
    db: Session, *, agent_id: str, run_id: str, lease_seconds: int
) -> models.AgentSlot | None:
    slot = db.get(models.AgentSlot, agent_id)
    if slot is None or slot.status != SLOT_STATUS_RUNNING:
        return None
    slot.locked_by_run_id = run_id
    slot.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    db.commit()
    db.refresh(slot)
    return slot


def extend_resident_slot_lease(
    db: Session, *, agent_id: str, run_id: str, lease_seconds: int
) -> models.AgentSlot | None:
    slot = db.get(models.AgentSlot, agent_id)
    if slot is None or slot.locked_by_run_id != run_id:
        return None
    slot.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    db.commit()
    db.refresh(slot)
    return slot


def complete_resident_slot_run(
    db: Session,
    *,
    agent_id: str,
    run_id: str,
    heartbeat_interval_seconds: int,
    next_tick_at: datetime | None = None,
    last_error: str | None = None,
) -> None:
    slot = db.get(models.AgentSlot, agent_id)
    if slot is None or slot.locked_by_run_id != run_id:
        return
    now = datetime.now(UTC)
    slot.status = SLOT_STATUS_ASSIGNED_IDLE
    slot.locked_by_run_id = None
    slot.lease_expires_at = None
    slot.last_run_at = now
    slot.next_tick_at = next_tick_at or now + timedelta(seconds=heartbeat_interval_seconds)
    slot.last_error = last_error[:LAST_ERROR_MAX_LENGTH] if last_error else None
    db.commit()
