"""Unfiltered canonical facts for projection eligibility in the same Session."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.relationships import models


def get_event(db: Session, event_id: str) -> models.SocialEvent | None:
    return db.get(models.SocialEvent, event_id)


def get_relationship(db: Session, relationship_state_id: str) -> models.RelationshipState | None:
    return db.get(models.RelationshipState, relationship_state_id)


def evidence_for_event(db: Session, *, event: models.SocialEvent) -> list[models.SocialEventEvidence]:
    return list(
        db.scalars(
            select(models.SocialEventEvidence).where(
                models.SocialEventEvidence.social_event_id == event.id
            )
        )
    )
