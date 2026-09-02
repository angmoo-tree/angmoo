"""Strict P8-L-K wire validation for Retrieval Router output.

The P8-L-J dataclasses are the stable semantic value objects.  This module is
the only supported boundary for converting untrusted provider JSON into those
objects.  It intentionally rejects identifiers, queries, arbitrary fields and
unbounded semantic values before any canonical lookup runs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domains.chat.domain.retrieval_intent import (
    RETRIEVAL_INTENT_VERSION,
    RetrievalAggregationKind,
    RetrievalAggregationMeaning,
    RetrievalContractError,
    RetrievalDecision,
    RetrievalEntityMention,
    RetrievalIntentEnvelope,
    RetrievalRelationshipMeaning,
    RetrievalRoute,
    RetrievalTimeKind,
    RetrievalTimeMeaning,
)


ROUTER_INTENTS = frozenset(
    {
        "current_context",
        "historical_recall",
        "relationship_state",
        "relationship_cause",
        "relationship_path",
        "relationship_comparison",
        "event_aggregation",
        "mixed_evidence",
        "clarification_required",
    }
)
ROUTER_ENTITY_ROLES = frozenset(
    {"counterpart", "mentioned_third_party", "actor", "target", "subject"}
)
ROUTER_RELATIONSHIP_DIMENSIONS = frozenset(
    {"affinity", "trust", "conflict", "familiarity", "support", "rivalry"}
)
ROUTER_RELATIONSHIP_POLARITIES = frozenset(
    {"positive", "negative", "neutral", "conflict", "improved", "worsened"}
)
ROUTER_COORDINATION_HINTS = frozenset(
    {"INDEPENDENT_PARALLEL", "GRAPH_THEN_CANONICAL", "CANONICAL_THEN_GRAPH"}
)
ROUTER_CLARIFICATION_SLOTS = frozenset(
    {
        "entity_identity",
        "pronoun_reference",
        "relationship_direction",
        "world",
        "time_scope",
        "counterpart",
    }
)
ROUTER_AGGREGATION_TARGETS = frozenset(
    {
        "events",
        "characters",
        "relationships",
        "character_sets",
        "relationship_states",
    }
)

_TOP_LEVEL_KEYS = frozenset(
    {
        "version",
        "decision",
        "route",
        "intent",
        "entities",
        "relationship",
        "time_scope",
        "aggregation",
        "coordination_hint",
        "clarification_slot",
    }
)
_FORBIDDEN_KEY_FRAGMENTS = (
    "owner_id",
    "world_id",
    "thread_id",
    "character_id",
    "source_id",
    "event_id",
    "sql",
    "cypher",
    "table",
    "column",
    "label",
    "property",
    "max_hops",
    "row_limit",
    "timeout",
    "token_budget",
)
_QUERY_MARKERS = (
    "select ",
    "insert ",
    "update ",
    "delete ",
    "drop ",
    "create ",
    "match (",
    "merge (",
    "detach delete",
    "return n",
)


def retrieval_router_response_schema() -> dict[str, Any]:
    """Return the provider-facing closed JSON schema.

    Google-compatible schemas do not consistently support every JSON Schema
    keyword.  The schema therefore constrains shape and enums while the parser
    below remains the final fail-closed authority for additionalProperties,
    cross-field invariants and forbidden values.
    """

    nullable_string = {"type": ["string", "null"]}
    return {
        "type": "object",
        "properties": {
            "version": {"type": "string", "enum": [RETRIEVAL_INTENT_VERSION]},
            "decision": {
                "type": "string",
                "enum": [value.value for value in RetrievalDecision],
            },
            "route": {
                "type": "string",
                "enum": [value.value for value in RetrievalRoute],
            },
            "intent": {"type": "string", "enum": sorted(ROUTER_INTENTS)},
            "entities": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "ref": {"type": "string"},
                        "mention": {"type": "string"},
                        "role": {
                            "type": "string",
                            "enum": sorted(ROUTER_ENTITY_ROLES),
                        },
                    },
                    "required": ["ref", "mention", "role"],
                },
            },
            "relationship": {
                "type": ["object", "null"],
                "properties": {
                    "perspective": {
                        "type": "string",
                        "enum": ["responding_character"],
                    },
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "dimension": {
                        "type": ["string", "null"],
                        "enum": [*sorted(ROUTER_RELATIONSHIP_DIMENSIONS), None],
                    },
                    "requested_polarity": {
                        "type": ["string", "null"],
                        "enum": [*sorted(ROUTER_RELATIONSHIP_POLARITIES), None],
                    },
                },
            },
            "time_scope": {
                "type": ["object", "null"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [value.value for value in RetrievalTimeKind],
                    },
                    "expression": nullable_string,
                },
            },
            "aggregation": {
                "type": ["object", "null"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [value.value for value in RetrievalAggregationKind],
                    },
                    "target_role": {
                        "type": "string",
                        "enum": sorted(ROUTER_AGGREGATION_TARGETS),
                    },
                },
            },
            "coordination_hint": {
                "type": ["string", "null"],
                "enum": [*sorted(ROUTER_COORDINATION_HINTS), None],
            },
            "clarification_slot": {
                "type": ["string", "null"],
                "enum": [*sorted(ROUTER_CLARIFICATION_SLOTS), None],
            },
        },
        "required": sorted(_TOP_LEVEL_KEYS),
    }


def parse_retrieval_intent_payload(payload: Mapping[str, Any]) -> RetrievalIntentEnvelope:
    """Parse one untrusted Router payload with exact-key validation."""

    if not isinstance(payload, Mapping):
        raise RetrievalContractError("retrieval_router_payload_not_object")
    _reject_forbidden_material(payload)
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, "retrieval_router_payload")

    version = _required_string(payload.get("version"), "version", maximum=64)
    decision = _enum(RetrievalDecision, payload.get("decision"), "decision")
    route = _enum(RetrievalRoute, payload.get("route"), "route")
    intent = _closed_string(payload.get("intent"), ROUTER_INTENTS, "intent")

    raw_entities = payload.get("entities")
    if not isinstance(raw_entities, Sequence) or isinstance(
        raw_entities, (str, bytes, bytearray)
    ):
        raise RetrievalContractError("retrieval_router_entities_invalid")
    if len(raw_entities) > 4:
        raise RetrievalContractError("retrieval_router_entity_limit_exceeded")
    entities: list[RetrievalEntityMention] = []
    for raw_entity in raw_entities:
        entity = _object(raw_entity, "entity")
        _require_exact_keys(entity, {"ref", "mention", "role"}, "entity")
        entities.append(
            RetrievalEntityMention(
                ref=_required_string(entity.get("ref"), "entity_ref", maximum=64),
                mention=_required_string(
                    entity.get("mention"), "entity_mention", maximum=160
                ),
                role=_closed_string(
                    entity.get("role"), ROUTER_ENTITY_ROLES, "entity_role"
                ),
            )
        )

    relationship = _parse_relationship(payload.get("relationship"))
    time_scope = _parse_time_scope(payload.get("time_scope"))
    aggregation = _parse_aggregation(payload.get("aggregation"))
    coordination_hint = _optional_closed_string(
        payload.get("coordination_hint"),
        ROUTER_COORDINATION_HINTS,
        "coordination_hint",
    )
    clarification_slot = _optional_closed_string(
        payload.get("clarification_slot"),
        ROUTER_CLARIFICATION_SLOTS,
        "clarification_slot",
    )

    envelope = RetrievalIntentEnvelope(
        version=version,
        decision=decision,
        route=route,
        intent=intent,
        entities=tuple(entities),
        relationship=relationship,
        time_scope=time_scope,
        aggregation=aggregation,
        coordination_hint=coordination_hint,
        clarification_slot=clarification_slot,
    )
    if route is RetrievalRoute.BOTH and coordination_hint is None:
        raise RetrievalContractError("retrieval_router_both_coordination_required")
    if route is not RetrievalRoute.BOTH and coordination_hint is not None:
        raise RetrievalContractError("retrieval_router_coordination_route_mismatch")
    if route is RetrievalRoute.CURRENT_CONTEXT and any(
        value is not None for value in (relationship, time_scope, aggregation)
    ):
        raise RetrievalContractError("retrieval_router_current_context_not_minimal")
    if route is not RetrievalRoute.CLARIFICATION and clarification_slot is not None:
        raise RetrievalContractError("retrieval_router_clarification_route_mismatch")
    return envelope


def _parse_relationship(value: Any) -> RetrievalRelationshipMeaning | None:
    if value is None:
        return None
    relationship = _object(value, "relationship")
    _require_exact_keys(
        relationship,
        {"perspective", "from", "to", "dimension", "requested_polarity"},
        "relationship",
    )
    if relationship.get("perspective") != "responding_character":
        raise RetrievalContractError("retrieval_router_perspective_invalid")
    dimension = _optional_closed_string(
        relationship.get("dimension"),
        ROUTER_RELATIONSHIP_DIMENSIONS,
        "relationship_dimension",
    )
    polarity = _optional_closed_string(
        relationship.get("requested_polarity"),
        ROUTER_RELATIONSHIP_POLARITIES,
        "relationship_polarity",
    )
    return RetrievalRelationshipMeaning(
        from_ref=_required_string(
            relationship.get("from"), "relationship_from", maximum=64
        ),
        to_ref=_required_string(
            relationship.get("to"), "relationship_to", maximum=64
        ),
        dimension=dimension,
        requested_polarity=polarity,
    )


def _parse_time_scope(value: Any) -> RetrievalTimeMeaning | None:
    if value is None:
        return None
    time_scope = _object(value, "time_scope")
    _require_exact_keys(time_scope, {"kind", "expression"}, "time_scope")
    kind = _enum(RetrievalTimeKind, time_scope.get("kind"), "time_kind")
    expression = _optional_string(
        time_scope.get("expression"), "time_expression", maximum=96
    )
    return RetrievalTimeMeaning(kind=kind, expression=expression)


def _parse_aggregation(value: Any) -> RetrievalAggregationMeaning | None:
    if value is None:
        return None
    aggregation = _object(value, "aggregation")
    _require_exact_keys(aggregation, {"kind", "target_role"}, "aggregation")
    return RetrievalAggregationMeaning(
        kind=_enum(
            RetrievalAggregationKind, aggregation.get("kind"), "aggregation_kind"
        ),
        target_role=_closed_string(
            aggregation.get("target_role"),
            ROUTER_AGGREGATION_TARGETS,
            "aggregation_target",
        ),
    )


def _reject_forbidden_material(value: Any, *, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise RetrievalContractError("retrieval_router_key_invalid")
            lowered = raw_key.casefold()
            if any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise RetrievalContractError("retrieval_router_forbidden_field")
            _reject_forbidden_material(nested, path=f"{path}.{raw_key}")
        return
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, nested in enumerate(value):
            _reject_forbidden_material(nested, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        normalized = " ".join(value.casefold().split())
        if any(marker in normalized for marker in _QUERY_MARKERS):
            raise RetrievalContractError("retrieval_router_raw_query_forbidden")


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RetrievalContractError(f"retrieval_router_{field}_invalid")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str] | frozenset[str], field: str
) -> None:
    if set(value) != set(expected):
        raise RetrievalContractError(f"retrieval_router_{field}_keys_invalid")


def _required_string(value: Any, field: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise RetrievalContractError(f"retrieval_router_{field}_invalid")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise RetrievalContractError(f"retrieval_router_{field}_invalid")
    return normalized


def _optional_string(value: Any, field: str, *, maximum: int) -> str | None:
    if value is None:
        return None
    return _required_string(value, field, maximum=maximum)


def _closed_string(value: Any, allowed: frozenset[str], field: str) -> str:
    normalized = _required_string(value, field, maximum=96)
    if normalized not in allowed:
        raise RetrievalContractError(f"retrieval_router_{field}_unknown")
    return normalized


def _optional_closed_string(
    value: Any, allowed: frozenset[str], field: str
) -> str | None:
    if value is None:
        return None
    return _closed_string(value, allowed, field)


def _enum(enum_type, value: Any, field: str):
    if not isinstance(value, str):
        raise RetrievalContractError(f"retrieval_router_{field}_invalid")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise RetrievalContractError(f"retrieval_router_{field}_unknown") from exc


__all__ = [
    "ROUTER_AGGREGATION_TARGETS",
    "ROUTER_CLARIFICATION_SLOTS",
    "ROUTER_COORDINATION_HINTS",
    "ROUTER_ENTITY_ROLES",
    "ROUTER_INTENTS",
    "ROUTER_RELATIONSHIP_DIMENSIONS",
    "ROUTER_RELATIONSHIP_POLARITIES",
    "parse_retrieval_intent_payload",
    "retrieval_router_response_schema",
]
