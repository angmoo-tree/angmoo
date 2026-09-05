"""Deterministic relationship candidate identifiers and payload copies."""
import hashlib
from typing import Any


def relationship_point_pair_key(
    source_character_id: str, recipient_character_id: str
) -> str:
    left, right = sorted([source_character_id, recipient_character_id])
    return f"{left}:{right}"


def relationship_point_source_signature(
    *,
    kind: str,
    recipient_character_id: str,
    source_character_id: str,
    source_post_id: str,
) -> str:
    return "|".join(
        [
            kind,
            recipient_character_id,
            source_character_id,
            source_post_id,
        ]
    )


def relationship_point_chain_id(
    *, source_post_id: str, recipient_character_id: str
) -> str:
    return (
        "rel:"
        + hashlib.sha256(
            f"{source_post_id}:{recipient_character_id}".encode("utf-8")
        ).hexdigest()[:24]
    )


def _relationship_point_payload(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return dict(value)
