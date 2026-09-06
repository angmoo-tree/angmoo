"""Directional state creation and per-source/day delta caps."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.ids import uuid7_string
from app.domains.relationships import models
from app.domains.relationships.contracts.events import EvidenceInput, EventWorld
from app.domains.relationships.repository import state as state_repository
from app.domains.relationships.policies.events import _local_day_bounds


def _relationship_state(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str,
) -> models.RelationshipState:
    state = state_repository.find_direction_for_update(db, world_id=world_id, actor_world_character_id=actor_world_character_id, target_world_character_id=target_world_character_id)
    if state is None:
        state = models.RelationshipState(
            id=uuid7_string(),
            world_id=world_id,
            actor_world_character_id=actor_world_character_id,
            target_world_character_id=target_world_character_id,
            familiarity=0,
            affinity=0,
            trust=0,
            tension=0,
            interaction_count=0,
            version=1,
        )
        db.add(state)
        db.flush()
    return state


def _delta_is_capped(
    db: Session,
    *,
    world: EventWorld,
    event: models.SocialEvent,
    evidence: EvidenceInput,
) -> bool:
    if event.target_world_character_id is None:
        return False
    if event.event_type in {"comment_created", "reply_created", "mention_created"}:
        start, end = _local_day_bounds(world, event.occurred_at)
        count = state_repository.daily_comment_change_count(db, event=event, start=start, end=end)
        return int(count or 0) >= 4
    if event.event_type not in {"like_added", "repost_added"}:
        return False
    source_post_id = evidence.target_post_id or evidence.source_post_id
    if source_post_id is None:
        return False
    prior = state_repository.prior_post_reaction_change(db, event=event, source_post_id=source_post_id)
    return prior is not None
