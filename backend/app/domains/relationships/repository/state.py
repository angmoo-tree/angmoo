"""Relationships-owned canonical queries in the caller Session."""
from datetime import datetime
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.domains.relationships import models


def find_direction_for_update(db: Session, *, world_id: str, actor_world_character_id: str, target_world_character_id: str) -> models.RelationshipState | None:
    return db.scalar(
        select(models.RelationshipState)
        .where(
            models.RelationshipState.world_id == world_id,
            models.RelationshipState.actor_world_character_id
            == actor_world_character_id,
            models.RelationshipState.target_world_character_id
            == target_world_character_id,
        )
        .with_for_update()
    )


def daily_comment_change_count(db: Session, *, event: models.SocialEvent, start: datetime, end: datetime) -> int | None:
    return db.scalar(
            select(func.count(models.RelationshipStateChange.id))
            .join(
                models.SocialEvent,
                models.SocialEvent.id == models.RelationshipStateChange.social_event_id,
            )
            .where(
                models.RelationshipStateChange.world_id == event.world_id,
                models.RelationshipStateChange.actor_world_character_id
                == event.actor_world_character_id,
                models.RelationshipStateChange.target_world_character_id
                == event.target_world_character_id,
                models.RelationshipStateChange.applied.is_(True),
                models.SocialEvent.event_type.in_(
                    ("comment_created", "reply_created", "mention_created")
                ),
                models.SocialEvent.occurred_at >= start,
                models.SocialEvent.occurred_at < end,
            )
        )


def prior_post_reaction_change(db: Session, *, event: models.SocialEvent, source_post_id: str) -> str | None:
    return db.scalar(
        select(models.RelationshipStateChange.id)
        .join(
            models.SocialEvent,
            models.SocialEvent.id == models.RelationshipStateChange.social_event_id,
        )
        .join(
            models.SocialEventEvidence,
            models.SocialEventEvidence.social_event_id == models.SocialEvent.id,
        )
        .where(
            models.RelationshipStateChange.world_id == event.world_id,
            models.RelationshipStateChange.actor_world_character_id
            == event.actor_world_character_id,
            models.RelationshipStateChange.target_world_character_id
            == event.target_world_character_id,
            models.RelationshipStateChange.applied.is_(True),
            models.SocialEvent.event_type == event.event_type,
            models.SocialEventEvidence.target_post_id == source_post_id,
            models.SocialEvent.id != event.id,
        )
        .limit(1)
    )
