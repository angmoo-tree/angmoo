"""Canonical observation evidence queries; no transaction ownership."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.domains.relationships import models
from app.domains.relationships.contracts.observations import ObservationPost


def get_event(db: Session, event_id: str) -> models.SocialEvent | None:
    return db.get(models.SocialEvent, event_id)


def find_matching_evidence(db: Session, *, source_event: models.SocialEvent, source_post: ObservationPost) -> str | None:
    return db.scalar(
        select(models.SocialEventEvidence.id).where(
            models.SocialEventEvidence.social_event_id == source_event.id,
            or_(
                models.SocialEventEvidence.source_post_id == source_post.id,
                models.SocialEventEvidence.target_post_id == source_post.id,
                models.SocialEventEvidence.root_post_id == source_post.id,
                (
                    (models.SocialEventEvidence.source_object_type == "post")
                    & (
                        models.SocialEventEvidence.source_object_id
                        == source_post.id
                    )
                ),
            ),
        )
    )


def find_source_event_for_post(db: Session, *, world_id: str, post: ObservationPost) -> models.SocialEvent | None:
    return db.scalar(
        select(models.SocialEvent)
        .join(
            models.SocialEventEvidence,
            models.SocialEventEvidence.social_event_id == models.SocialEvent.id,
        )
        .where(
            models.SocialEvent.world_id == world_id,
            models.SocialEvent.actor_world_character_id
            == post.author_world_character_id,
            models.SocialEvent.result == "succeeded",
            models.SocialEventEvidence.source_post_id == post.id,
        )
        .order_by(models.SocialEvent.occurred_at.desc(), models.SocialEvent.id.desc())
        .limit(1)
    )


def find_first_evidence(db: Session, *, source_event: models.SocialEvent) -> models.SocialEventEvidence | None:
    return db.scalar(
        select(models.SocialEventEvidence)
        .where(models.SocialEventEvidence.social_event_id == source_event.id)
        .order_by(models.SocialEventEvidence.created_at, models.SocialEventEvidence.id)
        .limit(1)
    )
