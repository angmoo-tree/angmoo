"""Immutable identity for one observer's projection of a source event."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping

from app.domains.relationships.constants import OBSERVATION_RELATIONSHIP_PAYLOAD_VERSION
from app.domains.relationships.exceptions import ObservationOutboxIntegrityError


@dataclass(frozen=True)
class ObservationOutboxValues:
    world_id: str
    source_event_id: str
    relationship_state_id: str
    projection_type: str
    payload_version: str
    payload: dict[str, str]
    source_signature: str
    dedupe_key: str


def observation_dedupe_key(source_event_id: str, relationship_state_id: str) -> str:
    value = (
        f"relationship_state|{source_event_id}|"
        f"{OBSERVATION_RELATIONSHIP_PAYLOAD_VERSION}|{relationship_state_id}"
    )
    return sha256(value.encode("utf-8")).hexdigest()


def build_observation_outbox_values(
    *, world_id: str, source_event_id: str, observer_id: str,
    target_id: str, relationship_state_id: str,
) -> ObservationOutboxValues:
    payload = {
        "world_id": world_id,
        "source_event_id": source_event_id,
        "actor_world_character_id": observer_id,
        "target_world_character_id": target_id,
        "relationship_state_id": relationship_state_id,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return ObservationOutboxValues(
        world_id=world_id,
        source_event_id=source_event_id,
        relationship_state_id=relationship_state_id,
        projection_type="relationship_state",
        payload_version=OBSERVATION_RELATIONSHIP_PAYLOAD_VERSION,
        payload=payload,
        source_signature=sha256(canonical.encode("utf-8")).hexdigest(),
        dedupe_key=observation_dedupe_key(source_event_id, relationship_state_id),
    )


def validate_observation_outbox(
    existing: Mapping[str, object], expected: ObservationOutboxValues,
) -> None:
    for name in (
        "world_id", "source_event_id", "relationship_state_id",
        "projection_type", "payload_version", "dedupe_key",
    ):
        if existing.get(name) != getattr(expected, name):
            raise ObservationOutboxIntegrityError("observation_outbox_identity_mismatch")
    if (existing.get("payload") != expected.payload
        or existing.get("source_signature") != expected.source_signature):
        raise ObservationOutboxIntegrityError("observation_outbox_payload_mismatch")
