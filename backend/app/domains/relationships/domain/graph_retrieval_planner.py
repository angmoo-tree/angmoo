"""Strict graph-only provider schema and parser for P8-L-M."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.domains.relationships.domain.graph_retrieval_plan import (
    GRAPH_PLAN_VERSION,
    MAX_GRAPH_PLAN_STEPS,
    GraphPlanContractError,
    GraphPlanStep,
    GraphRetrievalPlan,
)
from app.domains.relationships.graph_recall.contracts import (
    GraphRecallDirection,
    GraphRecallOperation,
    GraphRecallRanking,
)


_OPAQUE_REF_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_INPUT_REF_RE = re.compile(
    r"^(?P<step>[a-z][a-z0-9_]{0,47})\.world_character_refs$"
)
_TOP_LEVEL_KEYS = frozenset(
    {"version", "request_id", "envelope_version", "envelope_hash", "steps"}
)
_STEP_KEYS = frozenset({"id", "operation", "input_ref", "parameters"})
_GRAPH_OPERATION_VALUES = frozenset(
    operation.value for operation in GraphRecallOperation
)
_DIRECTION_VALUES = frozenset(direction.value for direction in GraphRecallDirection)
_RANKING_VALUES = frozenset(ranking.value for ranking in GraphRecallRanking)
_COUNTERPART_OPERATIONS = frozenset(
    {
        GraphRecallOperation.DIRECT_RELATIONSHIP.value,
        GraphRecallOperation.RELATIONSHIP_EVIDENCE.value,
        GraphRecallOperation.SHARED_NEIGHBORS.value,
        GraphRecallOperation.SHORTEST_PATH.value,
    }
)
_PARAMETERS_BY_OPERATION: dict[str, frozenset[str]] = {
    GraphRecallOperation.DIRECT_RELATIONSHIP.value: frozenset(
        {"counterpart_ref", "direction", "limit"}
    ),
    GraphRecallOperation.RELATIONSHIP_EVIDENCE.value: frozenset(
        {"counterpart_ref", "direction", "limit"}
    ),
    GraphRecallOperation.SHARED_NEIGHBORS.value: frozenset(
        {"counterpart_ref", "direction", "limit"}
    ),
    GraphRecallOperation.SHORTEST_PATH.value: frozenset(
        {"counterpart_ref", "direction", "max_hops", "limit"}
    ),
    GraphRecallOperation.RANK_RELATED_CHARACTERS.value: frozenset(
        {"direction", "ranking", "limit"}
    ),
    GraphRecallOperation.RELATIONSHIP_NEIGHBORHOOD.value: frozenset(
        {"direction", "depth", "limit"}
    ),
}
_FORBIDDEN_KEY_FRAGMENTS = (
    "owner_id",
    "world_id",
    "thread_id",
    "character_id",
    "relationship_state_id",
    "source_id",
    "event_id",
    "membership_id",
    "sql",
    "cypher",
    "table",
    "column",
    "label",
    "property",
    "relationship_type",
    "query",
    "where",
    "filter",
    "timeout",
    "token_budget",
)
_RAW_QUERY_MARKERS = (
    "select ",
    "insert ",
    "update ",
    "delete ",
    "drop ",
    "alter ",
    "create table",
    "match (",
    "merge (",
    "detach delete",
    "return n",
    "call db.",
    "pragma ",
)


def graph_retrieval_plan_response_schema() -> dict[str, Any]:
    """Return the graph-only portable provider response schema."""

    return {
        "type": "object",
        "properties": {
            "version": {"type": "string", "enum": [GRAPH_PLAN_VERSION]},
            "request_id": {"type": "string"},
            "envelope_version": {"type": "string"},
            "envelope_hash": {"type": "string"},
            "steps": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_GRAPH_PLAN_STEPS,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "operation": {
                            "type": "string",
                            "enum": sorted(_GRAPH_OPERATION_VALUES),
                        },
                        "input_ref": {"type": ["string", "null"]},
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "counterpart_ref": {"type": "string"},
                                "direction": {
                                    "type": "string",
                                    "enum": sorted(_DIRECTION_VALUES),
                                },
                                "ranking": {
                                    "type": "string",
                                    "enum": sorted(_RANKING_VALUES),
                                },
                                "max_hops": {"type": "integer"},
                                "depth": {"type": "integer"},
                                "limit": {"type": "integer"},
                            },
                        },
                    },
                    "required": sorted(_STEP_KEYS),
                },
            },
        },
        "required": sorted(_TOP_LEVEL_KEYS),
    }


def parse_graph_retrieval_plan_payload(
    payload: Mapping[str, Any],
) -> GraphRetrievalPlan:
    """Convert one untrusted provider payload into a strict typed graph plan."""

    if not isinstance(payload, Mapping):
        raise GraphPlanContractError("graph_plan_payload_not_object")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, "payload")
    _reject_forbidden_material(payload, path="root")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, Sequence) or isinstance(
        raw_steps, (str, bytes, bytearray)
    ):
        raise GraphPlanContractError("graph_plan_steps_invalid")
    if not 1 <= len(raw_steps) <= MAX_GRAPH_PLAN_STEPS:
        raise GraphPlanContractError("graph_plan_step_limit_invalid")

    steps: list[GraphPlanStep] = []
    seen: set[str] = set()
    for raw_step in raw_steps:
        step = _object(raw_step, "step")
        _require_exact_keys(step, _STEP_KEYS, "step")
        step_id = _required_string(step.get("id"), "step_id", maximum=48)
        if step_id in seen:
            raise GraphPlanContractError("graph_plan_step_id_duplicate")
        operation = _required_string(step.get("operation"), "operation", maximum=64)
        if operation not in _GRAPH_OPERATION_VALUES:
            raise GraphPlanContractError("graph_plan_operation_unknown")
        input_ref = _optional_string(step.get("input_ref"), "input_ref", maximum=96)
        parameters = _parse_parameters(operation, step.get("parameters"))
        _validate_step_shape(
            operation=operation,
            input_ref=input_ref,
            parameters=dict(parameters),
            seen=seen,
        )
        steps.append(
            GraphPlanStep(
                id=step_id,
                operation=operation,
                input_ref=input_ref,
                parameters=parameters,
            )
        )
        seen.add(step_id)

    return GraphRetrievalPlan(
        version=_required_string(payload.get("version"), "version", maximum=64),
        request_id=_required_string(
            payload.get("request_id"), "request_id", maximum=128
        ),
        envelope_version=_required_string(
            payload.get("envelope_version"), "envelope_version", maximum=64
        ),
        envelope_hash=_required_hash(payload.get("envelope_hash")),
        steps=tuple(steps),
    )


def _parse_parameters(
    operation: str, value: Any
) -> tuple[tuple[str, str | int | bool], ...]:
    parameters = _object(value, "parameters")
    allowed = _PARAMETERS_BY_OPERATION[operation]
    if not set(parameters) <= allowed:
        raise GraphPlanContractError("graph_plan_parameter_forbidden")

    normalized: list[tuple[str, str | int | bool]] = []
    for key in sorted(parameters):
        raw = parameters[key]
        if key == "counterpart_ref":
            ref = _required_string(raw, key, maximum=64)
            if not _OPAQUE_REF_RE.fullmatch(ref):
                raise GraphPlanContractError("graph_plan_entity_ref_invalid")
            normalized.append((key, ref))
        elif key == "direction":
            direction = _required_string(raw, key, maximum=16)
            if direction not in _DIRECTION_VALUES:
                raise GraphPlanContractError("graph_plan_direction_invalid")
            normalized.append((key, direction))
        elif key == "ranking":
            ranking = _required_string(raw, key, maximum=16)
            if ranking not in _RANKING_VALUES:
                raise GraphPlanContractError("graph_plan_ranking_invalid")
            normalized.append((key, ranking))
        elif key == "max_hops":
            if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 3:
                raise GraphPlanContractError("graph_plan_hops_invalid")
            normalized.append((key, raw))
        elif key == "depth":
            if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 2:
                raise GraphPlanContractError("graph_plan_depth_invalid")
            normalized.append((key, raw))
        elif key == "limit":
            if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 50:
                raise GraphPlanContractError("graph_plan_limit_invalid")
            normalized.append((key, raw))
        else:  # pragma: no cover - exact operation allowlist makes unreachable
            raise GraphPlanContractError("graph_plan_parameter_forbidden")
    return tuple(normalized)


def _validate_step_shape(
    *,
    operation: str,
    input_ref: str | None,
    parameters: Mapping[str, str | int | bool],
    seen: set[str],
) -> None:
    if "direction" not in parameters:
        raise GraphPlanContractError("graph_plan_direction_required")

    if operation in _COUNTERPART_OPERATIONS:
        has_counterpart = "counterpart_ref" in parameters
        has_input = input_ref is not None
        if has_counterpart == has_input:
            raise GraphPlanContractError("graph_plan_counterpart_binding_invalid")
        if has_input:
            match = _INPUT_REF_RE.fullmatch(input_ref or "")
            if match is None or match.group("step") not in seen:
                raise GraphPlanContractError("graph_plan_reference_invalid")
    elif input_ref is not None or "counterpart_ref" in parameters:
        raise GraphPlanContractError("graph_plan_counterpart_forbidden")

    if operation == GraphRecallOperation.SHORTEST_PATH.value and (
        "max_hops" not in parameters
    ):
        raise GraphPlanContractError("graph_plan_hops_required")
    if operation == GraphRecallOperation.RANK_RELATED_CHARACTERS.value and (
        "ranking" not in parameters
    ):
        raise GraphPlanContractError("graph_plan_ranking_required")
    if operation == GraphRecallOperation.RELATIONSHIP_NEIGHBORHOOD.value and (
        "depth" not in parameters
    ):
        raise GraphPlanContractError("graph_plan_depth_required")


def _reject_forbidden_material(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise GraphPlanContractError("graph_plan_key_invalid")
            lowered = raw_key.casefold()
            if not (path == "root" and lowered == "request_id") and any(
                fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS
            ):
                raise GraphPlanContractError("graph_plan_forbidden_field")
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
        if any(marker in normalized for marker in _RAW_QUERY_MARKERS):
            raise GraphPlanContractError("graph_plan_raw_query_forbidden")
        if normalized.startswith(("canonical.", "workflow.")):
            raise GraphPlanContractError("graph_plan_cross_axis_ref_forbidden")


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphPlanContractError(f"graph_plan_{field}_invalid")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str] | frozenset[str], field: str
) -> None:
    if set(value) != set(expected):
        raise GraphPlanContractError(f"graph_plan_{field}_keys_invalid")


def _required_string(value: Any, field: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise GraphPlanContractError(f"graph_plan_{field}_invalid")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise GraphPlanContractError(f"graph_plan_{field}_invalid")
    return normalized


def _optional_string(value: Any, field: str, *, maximum: int) -> str | None:
    if value is None:
        return None
    return _required_string(value, field, maximum=maximum)


def _required_hash(value: Any) -> str:
    normalized = _required_string(value, "envelope_hash", maximum=64)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise GraphPlanContractError("graph_plan_envelope_hash_invalid")
    return normalized


__all__ = [
    "graph_retrieval_plan_response_schema",
    "parse_graph_retrieval_plan_payload",
]
