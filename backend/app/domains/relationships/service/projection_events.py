"""Outbox payload selection and enqueueing within the source transaction."""
from hashlib import sha256
import json
from typing import Literal
from sqlalchemy.orm import Session
from app.core.ids import uuid7_string
from app.domains.relationships import models
from app.domains.relationships.constants import GRAPH_PAYLOAD_VERSION, SOURCE_EXCLUSION_PAYLOAD_VERSION
from app.domains.relationships.repository import events as event_repository


def _enqueue_outbox(
    db: Session,
    *,
    event: models.SocialEvent,
    relationship_state: models.RelationshipState | None,
) -> models.GraphProjectionOutbox:
    if event.event_type in {
        "joint_proposed",
        "joint_declined",
        "joint_cancelled",
        "joint_started",
    }:
        projection_type = "source_exclusion"
    elif relationship_state is not None:
        projection_type = "relationship_state"
    else:
        projection_type = "social_event"
    payload: dict[str, object] = {
        "world_id": event.world_id,
        "source_event_id": event.id,
        "actor_world_character_id": event.actor_world_character_id,
        "target_world_character_id": event.target_world_character_id,
    }
    if relationship_state is not None:
        payload["relationship_state_id"] = relationship_state.id
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = sha256(canonical.encode("utf-8")).hexdigest()
    dedupe_key = sha256(
        f"{projection_type}|{event.id}|{GRAPH_PAYLOAD_VERSION}".encode("utf-8")
    ).hexdigest()
    existing = event_repository.find_outbox_by_dedupe(db, dedupe_key=dedupe_key)
    if existing is not None:
        return existing
    row = models.GraphProjectionOutbox(
        id=uuid7_string(),
        world_id=event.world_id,
        source_event_id=event.id,
        projection_type=projection_type,
        payload_version=GRAPH_PAYLOAD_VERSION,
        payload=payload,
        source_signature=signature,
        dedupe_key=dedupe_key,
        status="pending",
        attempt_count=0,
    )
    db.add(row)
    return row


def _enqueue_source_exclusion_outbox(
    db: Session,
    *,
    event: models.SocialEvent,
    reason: Literal["source_deleted", "source_hidden"],
) -> models.GraphProjectionOutbox:
    projection_type = "source_exclusion"
    payload: dict[str, object] = {
        "world_id": event.world_id,
        "source_event_id": event.id,
        "reason": reason,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = sha256(canonical.encode("utf-8")).hexdigest()
    dedupe_key = sha256(
        (
            f"{projection_type}|{event.id}|"
            f"{SOURCE_EXCLUSION_PAYLOAD_VERSION}"
        ).encode("utf-8")
    ).hexdigest()
    existing = event_repository.find_outbox_by_dedupe(db, dedupe_key=dedupe_key)
    if existing is not None:
        return existing
    row = models.GraphProjectionOutbox(
        id=uuid7_string(),
        world_id=event.world_id,
        source_event_id=event.id,
        projection_type=projection_type,
        payload_version=SOURCE_EXCLUSION_PAYLOAD_VERSION,
        payload=payload,
        source_signature=signature,
        dedupe_key=dedupe_key,
        status="pending",
        attempt_count=0,
    )
    db.add(row)
    return row
