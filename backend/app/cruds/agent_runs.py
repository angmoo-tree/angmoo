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
