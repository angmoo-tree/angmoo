"""Queries over relationship response candidates, using the caller Session."""
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.domains.relationships import models
from app.domains.relationships.constants import RELATIONSHIP_POINT_ACTIVE_STATUSES, RELATIONSHIP_POINT_PENDING


def find_by_signature(db: Session, *, source_signature: str) -> models.AgentRelationshipPoint | None:
    return db.scalar(
        select(models.AgentRelationshipPoint).where(
            models.AgentRelationshipPoint.source_signature == source_signature
        )
    )


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


def list_expired(db: Session, *, now: datetime) -> list[models.AgentRelationshipPoint]:
    return list(
        db.scalars(
            select(models.AgentRelationshipPoint).where(
                models.AgentRelationshipPoint.status.in_(
                    RELATIONSHIP_POINT_ACTIVE_STATUSES
                ),
                models.AgentRelationshipPoint.expires_at <= now,
            )
        )
    )


def list_pending(db: Session, *, recipient_character_id: str, now: datetime, limit: int) -> list[models.AgentRelationshipPoint]:
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
