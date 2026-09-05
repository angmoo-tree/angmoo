"""Admission and lifecycle of relationship response candidates.

The original explicit commits belong to these operations even inside a caller's
deferred-write context; duplicate recovery rolls back before reading the winner.
"""
from datetime import datetime
from typing import Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.domains.relationships import models
from app.domains.relationships.repository import points as repository
from app.domains.relationships.constants import (
    RELATIONSHIP_POINT_KINDS, RELATIONSHIP_POINT_PENDING, RELATIONSHIP_POINT_SELECTED, RELATIONSHIP_POINT_CONSUMED, RELATIONSHIP_POINT_EXPIRED, RELATIONSHIP_POINT_FAILED, RELATIONSHIP_POINT_ACTIVE_STATUSES,
)
from app.domains.relationships.utils.points import (
    relationship_point_pair_key, relationship_point_source_signature, relationship_point_chain_id, _relationship_point_payload,
)


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
    existing = repository.find_by_signature(db, source_signature=source_signature)
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
        existing = repository.find_by_signature(db, source_signature=source_signature)
        return existing, "duplicate"
    db.refresh(point)
    return point, None


def expire_relationship_points(db: Session, *, now: datetime) -> int:
    points = repository.list_expired(db, now=now)
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
    return repository.list_pending(db, recipient_character_id=recipient_character_id, now=now, limit=limit)


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
