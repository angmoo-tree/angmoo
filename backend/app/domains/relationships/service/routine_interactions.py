"""Canonical successful reply eligibility and directional relationship band selection."""

from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.relationships.models import social as models
from app.domains.relationships.contracts.routine_interactions import (
    RoutineInteractionReferences,
)
from app.domains.relationships.repository import routine_interactions as repository
from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput


def _relationship_band(state: models.RelationshipState | None) -> str:
    if state is None:
        return "new"
    if state.trust >= 45 and state.affinity >= 35 and (state.familiarity >= 50):
        return "trusted"
    if state.affinity >= 25 and state.familiarity >= 30:
        return "close"
    if state.familiarity >= 10:
        return "familiar"
    return "new"


class CanonicalRoutineInteractionService:
    """Load only canonical successful comments/replies for the next P4 beat."""

    def __init__(self, references: RoutineInteractionReferences) -> None:
        self.references = references

    def candidates(
        self,
        db: Session,
        *,
        world_id: str,
        consumer_world_character_id: str,
        episode_id: str,
        after: datetime,
        before: datetime,
    ) -> list[RoutineInteractionInput]:
        rows = repository.reply_event_rows(
            db,
            world_id=world_id,
            consumer_world_character_id=consumer_world_character_id,
            after=after,
            before=before,
        )
        result: list[RoutineInteractionInput] = []
        for event, evidence in rows:
            if event.actor_world_character_id == consumer_world_character_id:
                continue
            source_post_id = evidence.source_post_id
            target_post_id = evidence.target_post_id or evidence.root_post_id
            if source_post_id is None or target_post_id is None:
                continue
            source_post = self.references.get_post(db, source_post_id)
            target_post = self.references.get_post(db, target_post_id)
            actor = self.references.get_world_character(
                db, event.actor_world_character_id
            )
            if (
                source_post is None
                or target_post is None
                or actor is None
                or (source_post.world_id != world_id)
                or (target_post.world_id != world_id)
                or (source_post.deleted_at is not None)
                or (target_post.deleted_at is not None)
                or (source_post.report_hidden_at is not None)
                or (target_post.report_hidden_at is not None)
                or (source_post.visibility != "public")
                or (target_post.visibility != "public")
                or (
                    source_post.author_world_character_id
                    != event.actor_world_character_id
                )
                or (
                    target_post.author_world_character_id != consumer_world_character_id
                )
                or (source_post.reply_to_post_id != target_post.id)
                or (actor.status != "active")
            ):
                continue
            membership = self.references.get_membership(db, actor.membership_id)
            if (
                membership is None
                or membership.world_id != world_id
                or membership.status != "active"
                or self.references.pair_blocked(
                    db,
                    world_id=world_id,
                    first_id=consumer_world_character_id,
                    second_id=event.actor_world_character_id,
                )
            ):
                continue
            relationship = repository.directional_relationship(
                db,
                world_id=world_id,
                consumer_world_character_id=consumer_world_character_id,
                actor_world_character_id=event.actor_world_character_id,
            )
            result.append(
                RoutineInteractionInput(
                    source_event_id=event.id,
                    world_id=world_id,
                    consumer_world_character_id=consumer_world_character_id,
                    actor_world_character_id=event.actor_world_character_id,
                    excerpt=source_post.body,
                    occurred_at=event.occurred_at,
                    directness=100 if event.event_type == "reply_created" else 90,
                    episode_relevance=100
                    if target_post.activity_episode_id == episode_id
                    else 60,
                    relationship_band=_relationship_band(relationship),
                )
            )
        result.extend(
            (
                RoutineInteractionInput(
                    source_event_id=candidate.source_event_id,
                    world_id=candidate.world_id,
                    consumer_world_character_id=candidate.consumer_world_character_id,
                    actor_world_character_id=candidate.actor_world_character_id,
                    excerpt=candidate.excerpt,
                    occurred_at=candidate.occurred_at,
                    directness=candidate.directness,
                    episode_relevance=candidate.episode_relevance,
                    relationship_band=candidate.relationship_band,
                )
                for candidate in self.references.manual_inbox_candidates(
                    db,
                    world_id=world_id,
                    consumer_world_character_id=consumer_world_character_id,
                    episode_id=episode_id,
                    after=after,
                    before=before,
                )
            )
        )
        return result
