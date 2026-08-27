"""Build domain projection commands from canonical SQLAlchemy facts."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.domains.relationships.projection.commands import (
    NoGraphMutationCommand,
    ProjectionCommand,
    ProjectionCommandError,
    RelationshipStateProjectionCommand,
    SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)


RELATIONSHIP_PAYLOAD_VERSION = "relationship-v1"
OBSERVATION_RELATIONSHIP_PAYLOAD_VERSION = "relationship-observation-v1"
SOURCE_EXCLUSION_PAYLOAD_VERSION = "source-exclusion-v1"
_IDENTIFIER_LIMIT = 128


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _validate_identifier(value: object, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value or len(value) > _IDENTIFIER_LIMIT:
        raise ProjectionCommandError("payload_invalid")
    return value


def _strict_payload(
    row: models.GraphProjectionOutbox,
) -> tuple[
    str,
    str,
    str,
    str | None,
    str | None,
    bool,
    str | None,
    str | None,
]:
    payload = row.payload
    if not isinstance(payload, dict):
        raise ProjectionCommandError("payload_invalid")
    if (
        row.projection_type == "source_exclusion"
        and row.payload_version == SOURCE_EXCLUSION_PAYLOAD_VERSION
    ):
        allowed = {"world_id", "source_event_id", "reason"}
        if set(payload) != allowed:
            raise ProjectionCommandError("payload_invalid")
        reason = payload.get("reason")
        if reason not in {"source_deleted", "source_hidden"}:
            raise ProjectionCommandError("payload_invalid")
        relationship_state_id = None
        observation_relationship = False
    elif row.payload_version in {
        RELATIONSHIP_PAYLOAD_VERSION,
        OBSERVATION_RELATIONSHIP_PAYLOAD_VERSION,
    }:
        allowed = {
            "world_id",
            "source_event_id",
            "actor_world_character_id",
            "target_world_character_id",
        }
        if row.projection_type == "relationship_state":
            allowed.add("relationship_state_id")
        if set(payload) != allowed:
            raise ProjectionCommandError("payload_invalid")
        reason = None
        relationship_state_id = _validate_identifier(
            payload.get("relationship_state_id"),
            nullable=row.projection_type != "relationship_state",
        )
        observation_relationship = (
            row.payload_version == OBSERVATION_RELATIONSHIP_PAYLOAD_VERSION
        )
    else:
        raise ProjectionCommandError("payload_version_unsupported")

    signature = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    if row.source_signature != signature:
        raise ProjectionCommandError("signature_mismatch")
    world_id = _validate_identifier(payload.get("world_id"))
    source_event_id = _validate_identifier(payload.get("source_event_id"))
    if world_id != row.world_id or source_event_id != row.source_event_id:
        raise ProjectionCommandError("world_mismatch")
    actor_id = _validate_identifier(
        payload.get("actor_world_character_id"), nullable=True
    )
    target_id = _validate_identifier(
        payload.get("target_world_character_id"), nullable=True
    )
    return (
        world_id,
        source_event_id,
        row.projection_type,
        relationship_state_id,
        reason,
        observation_relationship,
        actor_id,
        target_id,
    )


def _world_character(
    db: Session, *, world_id: str, world_character_id: str
) -> models.WorldCharacter:
    row = db.get(models.WorldCharacter, world_character_id)
    if row is None or row.world_id != world_id:
        raise ProjectionCommandError("world_mismatch")
    membership = db.get(models.WorldMembership, row.membership_id)
    if membership is None or membership.world_id != world_id:
        raise ProjectionCommandError("world_mismatch")
    return row


def _source_exclusion_reason(
    db: Session,
    *,
    event: models.SocialEvent,
) -> Literal["source_deleted", "source_hidden"] | None:
    if event.invalidation_reason in {"source_deleted", "source_hidden"}:
        return event.invalidation_reason
    evidence_rows = list(
        db.scalars(
            select(models.SocialEventEvidence).where(
                models.SocialEventEvidence.social_event_id == event.id
            )
        )
    )
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
        post = db.get(models.Post, post_id)
        if post is None or post.deleted_at is not None:
            return "source_deleted"
        if post.world_id != event.world_id:
            raise ProjectionCommandError("world_mismatch")
        if post.report_hidden_at is not None or post.visibility != "public":
            return "source_hidden"
    return None


def _event_command(
    db: Session, *, event: models.SocialEvent
) -> SocialEventProjectionCommand:
    actor = _world_character(
        db,
        world_id=event.world_id,
        world_character_id=event.actor_world_character_id,
    )
    target: models.WorldCharacter | None = None
    if event.target_world_character_id is not None:
        target = _world_character(
            db,
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
    replay_relationship_snapshot: bool = False,
) -> ProjectionCommand:
    row = db.get(models.GraphProjectionOutbox, outbox_id)
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
    event = db.get(models.SocialEvent, event_id)
    if event is None:
        raise ProjectionCommandError("source_missing", cancelled=True)
    if event.world_id != world_id:
        raise ProjectionCommandError("world_mismatch")
    if event.result != "succeeded":
        raise ProjectionCommandError("source_ineligible")

    if projection_type == "source_exclusion":
        reason = explicit_reason or _source_exclusion_reason(db, event=event)
        if reason is None:
            return NoGraphMutationCommand(
                world_id=world_id,
                event_id=event_id,
                reason="non_projected_audit_event",
            )
        return SourceExclusionProjectionCommand(world_id, event_id, reason)

    reason = _source_exclusion_reason(db, event=event)
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
    event_command = _event_command(db, event=event)
    if projection_type == "social_event":
        return event_command
    if projection_type != "relationship_state" or relationship_state_id is None:
        raise ProjectionCommandError("payload_invalid")

    relationship = db.get(models.RelationshipState, relationship_state_id)
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
    relationship_actor = _world_character(
        db,
        world_id=world_id,
        world_character_id=relationship.actor_world_character_id,
    )
    relationship_target = _world_character(
        db,
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
