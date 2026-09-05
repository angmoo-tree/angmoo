from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput
from app.runtime.social.sqlalchemy_inbox import candidates as manual_inbox_candidates


def _relationship_band(state: models.RelationshipState | None) -> str:
    if state is None:
        return "new"
    if state.trust >= 45 and state.affinity >= 35 and state.familiarity >= 50:
        return "trusted"
    if state.affinity >= 25 and state.familiarity >= 30:
        return "close"
    if state.familiarity >= 10:
        return "familiar"
    return "new"


def _blocked(
    db: Session, *, world_id: str, first_id: str, second_id: str
) -> bool:
    return (
        db.scalar(
            select(models.WorldCharacterBlock.id)
            .where(
                models.WorldCharacterBlock.world_id == world_id,
                or_(
                    (
                        models.WorldCharacterBlock.blocker_world_character_id
                        == first_id
                    )
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == second_id
                    ),
                    (
                        models.WorldCharacterBlock.blocker_world_character_id
                        == second_id
                    )
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == first_id
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )


class CanonicalRoutineInteractionSource:
    """Load only canonical successful comments/replies for the next P4 beat."""

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
        rows = db.execute(
            select(models.SocialEvent, models.SocialEventEvidence)
            .join(
                models.SocialEventEvidence,
                models.SocialEventEvidence.social_event_id
                == models.SocialEvent.id,
            )
            .where(
                models.SocialEvent.world_id == world_id,
                models.SocialEvent.target_world_character_id
                == consumer_world_character_id,
                models.SocialEvent.event_type.in_(
                    {"comment_created", "reply_created"}
                ),
                models.SocialEvent.result == "succeeded",
                models.SocialEvent.retrieval_status == "eligible",
                models.SocialEvent.occurred_at > after,
                models.SocialEvent.occurred_at <= before,
                models.SocialEventEvidence.source_object_type == "post",
            )
            .order_by(models.SocialEvent.occurred_at, models.SocialEvent.id)
        )
        result: list[RoutineInteractionInput] = []
        for event, evidence in rows:
            if event.actor_world_character_id == consumer_world_character_id:
                continue
            source_post_id = evidence.source_post_id
            target_post_id = evidence.target_post_id or evidence.root_post_id
            if source_post_id is None or target_post_id is None:
                continue
            source_post = db.get(models.Post, source_post_id)
            target_post = db.get(models.Post, target_post_id)
            actor = db.get(models.WorldCharacter, event.actor_world_character_id)
            if (
                source_post is None
                or target_post is None
                or actor is None
                or source_post.world_id != world_id
                or target_post.world_id != world_id
                or source_post.deleted_at is not None
                or target_post.deleted_at is not None
                or source_post.report_hidden_at is not None
                or target_post.report_hidden_at is not None
                or source_post.visibility != "public"
                or target_post.visibility != "public"
                or source_post.author_world_character_id
                != event.actor_world_character_id
                or target_post.author_world_character_id
                != consumer_world_character_id
                or source_post.reply_to_post_id != target_post.id
                or actor.status != "active"
            ):
                continue
            membership = db.get(models.WorldMembership, actor.membership_id)
            if (
                membership is None
                or membership.world_id != world_id
                or membership.status != "active"
                or _blocked(
                    db,
                    world_id=world_id,
                    first_id=consumer_world_character_id,
                    second_id=event.actor_world_character_id,
                )
            ):
                continue
            relationship = db.scalar(
                select(models.RelationshipState).where(
                    models.RelationshipState.world_id == world_id,
                    models.RelationshipState.actor_world_character_id
                    == consumer_world_character_id,
                    models.RelationshipState.target_world_character_id
                    == event.actor_world_character_id,
                )
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
                    episode_relevance=(
                        100
                        if target_post.activity_episode_id == episode_id
                        else 60
                    ),
                    relationship_band=_relationship_band(relationship),
                )
            )
        result.extend(
            RoutineInteractionInput(
                source_event_id=candidate.source_event_id,
                world_id=candidate.world_id,
                consumer_world_character_id=(
                    candidate.consumer_world_character_id
                ),
                actor_world_character_id=candidate.actor_world_character_id,
                excerpt=candidate.excerpt,
                occurred_at=candidate.occurred_at,
                directness=candidate.directness,
                episode_relevance=candidate.episode_relevance,
                relationship_band=candidate.relationship_band,
            )
            for candidate in manual_inbox_candidates(
                db,
                world_id=world_id,
                consumer_world_character_id=consumer_world_character_id,
                episode_id=episode_id,
                after=after,
                before=before,
            )
        )
        return result
