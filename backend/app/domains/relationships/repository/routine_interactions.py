"""Successful canonical event/evidence rows and directional relationship state reads."""

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.engine import Result
from sqlalchemy.orm import Session
from app.domains.relationships.models import social as models


def reply_event_rows(
    db: Session,
    *,
    world_id: str,
    consumer_world_character_id: str,
    after: datetime,
    before: datetime,
) -> Result[tuple[models.SocialEvent, models.SocialEventEvidence]]:
    return db.execute(
        select(models.SocialEvent, models.SocialEventEvidence)
        .join(
            models.SocialEventEvidence,
            models.SocialEventEvidence.social_event_id == models.SocialEvent.id,
        )
        .where(
            models.SocialEvent.world_id == world_id,
            models.SocialEvent.target_world_character_id == consumer_world_character_id,
            models.SocialEvent.event_type.in_({"comment_created", "reply_created"}),
            models.SocialEvent.result == "succeeded",
            models.SocialEvent.retrieval_status == "eligible",
            models.SocialEvent.occurred_at > after,
            models.SocialEvent.occurred_at <= before,
            models.SocialEventEvidence.source_object_type == "post",
        )
        .order_by(models.SocialEvent.occurred_at, models.SocialEvent.id)
    )


def directional_relationship(
    db: Session,
    *,
    world_id: str,
    consumer_world_character_id: str,
    actor_world_character_id: str,
) -> models.RelationshipState | None:
    return db.scalar(
        select(models.RelationshipState).where(
            models.RelationshipState.world_id == world_id,
            models.RelationshipState.actor_world_character_id
            == consumer_world_character_id,
            models.RelationshipState.target_world_character_id
            == actor_world_character_id,
        )
    )
