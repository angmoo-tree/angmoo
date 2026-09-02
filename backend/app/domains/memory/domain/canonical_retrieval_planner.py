"""P8-L-L provider schema and parser for canonical-only retrieval plans.

The generic plan value object arrived with P8-L-J and is frozen by that stage's
inventory. This module adds the L-stage provider boundary without weakening or
mutating the predecessor contract. It accepts only the nine P8-L-H canonical
recall operations, opaque semantic references and plain FTS search concepts.
Actual identifiers, SQL/schema material and Graph operations cannot cross this
wire.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.domains.memory.domain.canonical_retrieval_plan import (
    CANONICAL_PLAN_VERSION,
    MAX_CANONICAL_PLAN_STEPS,
    CanonicalPlanContractError,
    CanonicalPlanStep,
    CanonicalRetrievalPlan,
)
from app.domains.memory.domain.recall import CanonicalRecallOperation

MAX_CANONICAL_SEARCH_TEXT_CHARACTERS = 160
_OPAQUE_REF_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_INPUT_REF_RE = re.compile(r"^(?P<step>[a-z][a-z0-9_]{0,47})\.source_refs$")

_TOP_LEVEL_KEYS = frozenset(
    {"version", "request_id", "envelope_version", "envelope_hash", "steps"}
)
_STEP_KEYS = frozenset({"id", "operation", "input_ref", "parameters"})
_CANONICAL_OPERATION_VALUES = frozenset(
    operation.value for operation in CanonicalRecallOperation
)
_SEARCH_OPERATIONS = frozenset(
    {
        CanonicalRecallOperation.SEARCH_THREAD_MESSAGES.value,
        CanonicalRecallOperation.SEARCH_POSTS.value,
        CanonicalRecallOperation.SEARCH_MEMORY_ITEMS.value,
    }
)
_DEPENDENCY_OPERATIONS = frozenset(
    {
        CanonicalRecallOperation.CANONICAL_EVENT_DETAILS.value,
        CanonicalRecallOperation.GET_POST_THREAD.value,
    }
)
_PARAMETERS_BY_OPERATION: dict[str, frozenset[str]] = {
    CanonicalRecallOperation.SEARCH_THREAD_MESSAGES.value: frozenset(
        {"search_text", "counterpart_ref", "current_thread", "limit"}
    ),
    CanonicalRecallOperation.SEARCH_POSTS.value: frozenset(
        {"search_text", "counterpart_ref", "limit"}
    ),
    CanonicalRecallOperation.SEARCH_MEMORY_ITEMS.value: frozenset(
        {"search_text", "counterpart_ref", "limit"}
    ),
    CanonicalRecallOperation.LIST_SOCIAL_EVENTS.value: frozenset(
        {"counterpart_ref", "limit"}
    ),
    CanonicalRecallOperation.CANONICAL_EVENT_DETAILS.value: frozenset({"limit"}),
    CanonicalRecallOperation.GET_POST_THREAD.value: frozenset({"limit"}),
    CanonicalRecallOperation.LIST_ACTIVITY_EPISODES.value: frozenset(
        {"counterpart_ref", "limit"}
    ),
    CanonicalRecallOperation.LIST_RELATIONSHIP_CHANGES.value: frozenset(
        {"counterpart_ref", "limit"}
    ),
    CanonicalRecallOperation.GET_CHARACTER_SUMMARIES.value: frozenset(
        {"entity_ref", "limit"}
    ),
}
_FORBIDDEN_KEY_FRAGMENTS = (
    "owner_id",
    "world_id",
    "thread_id",
    "character_id",
    "source_id",
    "event_id",
    "membership_id",
    "sql",
    "cypher",
    "table",
    "column",
    "label",
    "property",
    "query",
    "where",
    "filter",
    "max_hops",
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
    "pragma ",
)


def canonical_retrieval_plan_response_schema() -> dict[str, Any]:
    """Return the canonical-only provider response schema.

    The direct provider supports only a portable JSON-Schema subset, so the
    parser remains authoritative for exact keys and cross-field invariants.
    """

    return {
        "type": "object",
        "properties": {
            "version": {"type": "string", "enum": [CANONICAL_PLAN_VERSION]},
            "request_id": {"type": "string"},
            "envelope_version": {"type": "string"},
            "envelope_hash": {"type": "string"},
            "steps": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_CANONICAL_PLAN_STEPS,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "operation": {
                            "type": "string",
                            "enum": sorted(_CANONICAL_OPERATION_VALUES),
                        },
                        "input_ref": {"type": ["string", "null"]},
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "search_text": {"type": "string"},
                                "counterpart_ref": {"type": "string"},
                                "entity_ref": {"type": "string"},
                                "current_thread": {"type": "boolean"},
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


def parse_canonical_retrieval_plan_payload(
    payload: Mapping[str, Any],
) -> CanonicalRetrievalPlan:
    """Convert one untrusted provider payload into a strict typed plan."""

    if not isinstance(payload, Mapping):
        raise CanonicalPlanContractError("canonical_plan_payload_not_object")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, "payload")
    _reject_forbidden_material(payload, path="root")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, Sequence) or isinstance(
        raw_steps, (str, bytes, bytearray)
    ):
        raise CanonicalPlanContractError("canonical_plan_steps_invalid")
    if not 1 <= len(raw_steps) <= MAX_CANONICAL_PLAN_STEPS:
        raise CanonicalPlanContractError("canonical_plan_step_limit_invalid")

    steps: list[CanonicalPlanStep] = []
    seen: set[str] = set()
    for raw_step in raw_steps:
        step = _object(raw_step, "step")
        _require_exact_keys(step, _STEP_KEYS, "step")
        step_id = _required_string(step.get("id"), "step_id", maximum=48)
        operation = _required_string(step.get("operation"), "operation", maximum=64)
        if operation not in _CANONICAL_OPERATION_VALUES:
            raise CanonicalPlanContractError("canonical_plan_operation_unknown")
        input_ref = _optional_string(step.get("input_ref"), "input_ref", maximum=96)
        parameters = _parse_parameters(operation, step.get("parameters"))
        _validate_step_shape(
            operation=operation,
            input_ref=input_ref,
            parameters=dict(parameters),
            seen=seen,
        )
        steps.append(
            CanonicalPlanStep(
                id=step_id,
                operation=operation,
                input_ref=input_ref,
                parameters=parameters,
            )
        )
        seen.add(step_id)

    return CanonicalRetrievalPlan(
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
        raise CanonicalPlanContractError("canonical_plan_parameter_forbidden")

    normalized: list[tuple[str, str | int | bool]] = []
    for key in sorted(parameters):
        raw = parameters[key]
        if key in {"counterpart_ref", "entity_ref"}:
            ref = _required_string(raw, key, maximum=64)
            if not _OPAQUE_REF_RE.fullmatch(ref):
                raise CanonicalPlanContractError("canonical_plan_entity_ref_invalid")
            normalized.append((key, ref))
        elif key == "search_text":
            text = _required_string(
                raw,
                key,
                maximum=MAX_CANONICAL_SEARCH_TEXT_CHARACTERS,
            )
            normalized.append((key, text))
        elif key == "current_thread":
            if not isinstance(raw, bool):
                raise CanonicalPlanContractError(
                    "canonical_plan_current_thread_invalid"
                )
            normalized.append((key, raw))
        elif key == "limit":
            if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 50:
                raise CanonicalPlanContractError("canonical_plan_limit_invalid")
            normalized.append((key, raw))
        else:  # pragma: no cover - exact allowlist above makes this unreachable
            raise CanonicalPlanContractError("canonical_plan_parameter_forbidden")
    return tuple(normalized)


def _validate_step_shape(
    *,
    operation: str,
    input_ref: str | None,
    parameters: Mapping[str, str | int | bool],
    seen: set[str],
) -> None:
    if operation in _SEARCH_OPERATIONS and "search_text" not in parameters:
        raise CanonicalPlanContractError("canonical_plan_search_text_required")
    if operation == CanonicalRecallOperation.GET_CHARACTER_SUMMARIES.value and (
        "entity_ref" not in parameters
    ):
        raise CanonicalPlanContractError("canonical_plan_entity_ref_required")

    if operation in _DEPENDENCY_OPERATIONS:
        if input_ref is None:
            raise CanonicalPlanContractError("canonical_plan_input_ref_required")
        match = _INPUT_REF_RE.fullmatch(input_ref)
        if match is None or match.group("step") not in seen:
            raise CanonicalPlanContractError("canonical_plan_reference_invalid")
    elif input_ref is not None:
        raise CanonicalPlanContractError("canonical_plan_input_ref_forbidden")


def _reject_forbidden_material(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise CanonicalPlanContractError("canonical_plan_key_invalid")
            lowered = raw_key.casefold()
            if not (path == "root" and lowered == "request_id") and any(
                fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS
            ):
                raise CanonicalPlanContractError("canonical_plan_forbidden_field")
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
            raise CanonicalPlanContractError("canonical_plan_raw_query_forbidden")
        if normalized.startswith(("graph.", "workflow.")):
            raise CanonicalPlanContractError("canonical_plan_cross_axis_ref_forbidden")


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CanonicalPlanContractError(f"canonical_plan_{field}_invalid")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str] | frozenset[str], field: str
) -> None:
    if set(value) != set(expected):
        raise CanonicalPlanContractError(f"canonical_plan_{field}_keys_invalid")


def _required_string(value: Any, field: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise CanonicalPlanContractError(f"canonical_plan_{field}_invalid")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise CanonicalPlanContractError(f"canonical_plan_{field}_invalid")
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
        raise CanonicalPlanContractError("canonical_plan_envelope_hash_invalid")
    return normalized


__all__ = [
    "MAX_CANONICAL_SEARCH_TEXT_CHARACTERS",
    "canonical_retrieval_plan_response_schema",
    "parse_canonical_retrieval_plan_payload",
]
