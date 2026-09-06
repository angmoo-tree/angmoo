"""Build graph commands only after canonical source and relationship checks."""
from __future__ import annotations
from typing import Literal
from sqlalchemy.orm import Session
from app.domains.relationships import models
from app.domains.relationships.contracts.projection_commands import (
    NoGraphMutationCommand, ProjectionCommand, ProjectionCommandError,
    ProjectionCommandReferences, ProjectionWorldCharacter,
    RelationshipStateProjectionCommand, SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)
from app.domains.relationships.policies.projection_commands import _strict_payload
from app.domains.relationships.repository import projection_commands as projection_repository
from app.domains.relationships.repository import projection_state as state_repository


def _source_exclusion_reason(
    db: Session,
    *,
    event: models.SocialEvent,
    references: ProjectionCommandReferences,
) -> Literal["source_deleted", "source_hidden"] | None:
    if event.invalidation_reason in {"source_deleted", "source_hidden"}:
        return event.invalidation_reason
    evidence_rows = projection_repository.evidence_for_event(db, event=event)
    for evidence in evidence_rows:
        post_id = (
            evidence.source_post_id
            or evidence.target_post_id
            or evidence.root_post_id
            or (
                evidence.source_object_id
                if evidence.source_object_type == "post"
                else None
            )
        )
        if post_id is None:
            continue
        post = references.get_post(post_id)
        if post is None or post.deleted_at is not None:
            return "source_deleted"
        if post.world_id != event.world_id:
            raise ProjectionCommandError("world_mismatch")
        if post.report_hidden_at is not None or post.visibility != "public":
            return "source_hidden"
    return None


def _event_command(
    db: Session, *, event: models.SocialEvent, references: ProjectionCommandReferences
) -> SocialEventProjectionCommand:
    actor = references.world_character(
        world_id=event.world_id,
        world_character_id=event.actor_world_character_id,
    )
    target: ProjectionWorldCharacter | None = None
    if event.target_world_character_id is not None:
        target = references.world_character(
            world_id=event.world_id,
            world_character_id=event.target_world_character_id,
        )
    return SocialEventProjectionCommand(
        world_id=event.world_id,
        event_id=event.id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        schema_version=event.schema_version,
        actor_world_character_id=actor.id,
        actor_character_id=actor.character_id,
        target_world_character_id=target.id if target else None,
        target_character_id=target.character_id if target else None,
    )


def build_projection_command(
    db: Session,
    *,
    outbox_id: str,
    references: ProjectionCommandReferences,
    replay_relationship_snapshot: bool = False,
) -> ProjectionCommand:
    row = state_repository.get_outbox(db, outbox_id)
    if row is None:
        raise ProjectionCommandError("source_missing", cancelled=True)
    (
        world_id,
        event_id,
        projection_type,
        relationship_state_id,
        explicit_reason,
        observation_relationship,
        payload_actor_id,
        payload_target_id,
    ) = _strict_payload(row)
    event = projection_repository.get_event(db, event_id)
    if event is None:
        raise ProjectionCommandError("source_missing", cancelled=True)
    if event.world_id != world_id:
        raise ProjectionCommandError("world_mismatch")
    if event.result != "succeeded":
        raise ProjectionCommandError("source_ineligible")

    if projection_type == "source_exclusion":
        reason = explicit_reason or _source_exclusion_reason(db, event=event, references=references)
        if reason is None:
            return NoGraphMutationCommand(
                world_id=world_id,
                event_id=event_id,
                reason="non_projected_audit_event",
            )
        return SourceExclusionProjectionCommand(world_id, event_id, reason)

    reason = _source_exclusion_reason(db, event=event, references=references)
    if event.retrieval_status == "audit_only" and not observation_relationship:
        return NoGraphMutationCommand(world_id, event_id, "event_audit_only")
    preserve_relationship = (
        replay_relationship_snapshot
        and projection_type == "relationship_state"
        and relationship_state_id is not None
        and reason in {"source_deleted", "source_hidden"}
    )
    if (
        event.retrieval_status == "excluded" or reason is not None
    ) and not preserve_relationship:
        return SourceExclusionProjectionCommand(
            world_id,
            event_id,
            reason or "source_hidden",
        )
    event_command = _event_command(db, event=event, references=references)
    if projection_type == "social_event":
        return event_command
    if projection_type != "relationship_state" or relationship_state_id is None:
        raise ProjectionCommandError("payload_invalid")

    relationship = projection_repository.get_relationship(db, relationship_state_id)
    if relationship is None:
        raise ProjectionCommandError("source_missing", cancelled=True)
    expected_actor_id = (
        payload_actor_id if observation_relationship else event.actor_world_character_id
    )
    expected_target_id = (
        payload_target_id if observation_relationship else event.target_world_character_id
    )
    if (
        relationship.world_id != world_id
        or relationship.actor_world_character_id != expected_actor_id
        or relationship.target_world_character_id != expected_target_id
    ):
        raise ProjectionCommandError("relationship_direction_mismatch")
    relationship_actor = references.world_character(
        world_id=world_id,
        world_character_id=relationship.actor_world_character_id,
    )
    relationship_target = references.world_character(
        world_id=world_id,
        world_character_id=relationship.target_world_character_id,
    )
    return RelationshipStateProjectionCommand(
        event=event_command,
        relationship_state_id=relationship.id,
        actor_world_character_id=relationship_actor.id,
        actor_character_id=relationship_actor.character_id,
        target_world_character_id=relationship_target.id,
        target_character_id=relationship_target.character_id,
        familiarity=relationship.familiarity,
        affinity=relationship.affinity,
        trust=relationship.trust,
        tension=relationship.tension,
        interaction_count=relationship.interaction_count,
        last_event_id=relationship.last_event_id,
        last_event_at=relationship.last_event_at,
        updated_at=relationship.updated_at,
        relationship_version=relationship.version,
    )
