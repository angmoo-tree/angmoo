"""Versioned payload shape, bounded identifiers and canonical signatures."""
from __future__ import annotations
from hashlib import sha256
import json
from app.domains.relationships.constants import (
    RELATIONSHIP_PAYLOAD_VERSION,
    OBSERVATION_RELATIONSHIP_PAYLOAD_VERSION,
    SOURCE_EXCLUSION_PAYLOAD_VERSION,
    _IDENTIFIER_LIMIT,
)
from app.domains.relationships.contracts.projection_commands import (
    ProjectionCommandError, ProjectionOutboxPayload,
)


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _validate_identifier(value: object, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value or len(value) > _IDENTIFIER_LIMIT:
        raise ProjectionCommandError("payload_invalid")
    return value


def _strict_payload(
    row: ProjectionOutboxPayload,
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
