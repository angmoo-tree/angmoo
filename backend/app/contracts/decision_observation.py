"""Bounded diagnostic transport. No domain decisions, provider calls or persistence."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
from math import isfinite
import re

from app.contracts.retrieval_observation import current, observe

VERSION = "decision-trace.v2"
scope = ContextVar("decision_observation_scope", default=("graph", "first", "planning"))
_EVENTS = frozenset({"selection_attempt", "selection_fields", "graph_input", "graph_step",
                     "graph_validation", "graph_execution", "graph_provider", "reference_failure", "reference_inputs", "resolved_references"})
_TEXT_FIELDS = frozenset({"status", "check", "validation_code", "normalized_code", "field_path",
    "finish_reason", "response_state", "operation", "function", "applied_rule", "validation_pass",
    "expected_direction", "returned_direction", "expected_counterpart", "returned_counterpart",
    "expected_identity", "returned_identity", "upstream_from", "upstream_to", "from_identity", "to_identity",
    "counterpart_check", "direction_check", "input_kind", "input_step", "step_ref", "repair_code", "repair_rule",
    "repair_digest", "prompt_digest", "schema_digest", "provider", "model", "thinking_level",
    "response_observed", "usage_observed", "dispatch_complete", "text_shape", "entities_state",
    "relationship_state", "aggregation_state", "perspective_state", "from_state", "to_state",
    "dimension_state", "polarity_state", "from_ref", "to_ref", "from_resolution", "to_resolution",
    "dimension", "polarity", "perspective", "aggregation_kind", "aggregation_target",
    "intent", "time_scope_state", "coordination_state", "execution_state", "ranking",
    "expected_values_supplied", "changed_fields", "shape_check", "from_is_subject", "to_is_subject", "wire_stage", "entities_stage", "relationship_stage", "meaning_stage", "coordination_stage", "agreement_stage"})
_NUMBER_FIELDS = frozenset({"step", "call", "tool_count", "response_chars", "entity_count", "extra_keys",
    "missing_keys", "max_output_tokens", "timeout_seconds", "input_tokens", "output_tokens", "thought_tokens",
    "total_tokens", "physical_attempts", "logical_calls", "limit", "max_hops", "depth", "plan_steps",
    "expected_ref_count", "returned_ref_length"})
_CODE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,95}$")
_REF_TEXT = frozenset({"value_type", "features_complete", "first_lower", "has_uppercase", "has_underscore", "has_space", "has_non_ascii", "has_other", "ref_alias"})
_TEXT_FIELDS |= _REF_TEXT | frozenset("received_" + k for k in _REF_TEXT) | frozenset({"input_stage", "failure_reason", "same_endpoint", "normalization_changed"})
_NUMBER_FIELDS |= frozenset({"entity_index", "value_length", "received_value_length"})


def closed(value, allowed, *, absent="not_reported"):
    if value is None:
        return absent
    return value if type(value) is str and value in allowed else "unknown"


def shape(value, *, present=True):
    if not present:
        return "missing"
    return {type(None): "null", bool: "boolean", int: "integer", float: "number",
            str: "string", list: "array", tuple: "array", dict: "object"}.get(type(value), "unknown")


def alias(kind, value):
    """Request-local names; the private lookup is never part of any payload."""
    target = current.get()
    if target is None or not target.detailed:
        return "not_captured"
    if type(value) is not str or not value or len(value) > 160:
        return "unresolved"
    if kind not in {"ref", "identity", "step"}:
        return "unknown"
    mapping = target.trace_aliases.setdefault(kind, {})
    if value not in mapping:
        if len(mapping) >= 32:
            return "alias_limit"
        mapping[value] = f"{kind}-{len(mapping) + 1}"
    return mapping[value]


@contextmanager
def decision_scope(axis, phase, validation_pass="planning"):
    token = scope.set((axis, phase, validation_pass))
    try:
        yield
    finally:
        scope.reset(token)


def emit(event, *, axis, phase, basic=None, **values):
    """Callers project domain values to closed codes before using this transport."""
    target = current.get()
    if target is None:
        return
    try:
        if event not in _EVENTS or axis not in {"graph", "supervisor"} or phase not in {"first", "repair", "execution"}:
            return
        target.trace_active = True
        if basic is not None:
            observe("decision_failure" if basic.get("status") == "rejected" else "decision_attempt",
                    axis=axis, phase=phase, **basic)
        if not target.detailed:
            return
        row = {"event": event, "trace_version": VERSION, "axis": axis, "phase": phase}
        for key, value in values.items():
            entity_field = re.fullmatch(r"entity_[1-4]_(ref|identity|role)", key)
            entity_number = re.fullmatch(r"entity_[1-4]_(candidates|safe)", key)
            if (key in _TEXT_FIELDS or entity_field) and type(value) is str and _CODE.fullmatch(value):
                row[key] = value
            elif (key in _NUMBER_FIELDS or entity_number) and type(value) in {int, float} and isfinite(value) and 0 <= value <= 1_000_000_000:
                row[key] = round(value, 3)
        # Keep rejection/attempt evidence ahead of verbose successful query details.
        candidate = [*target.details, row]
        while len(candidate) > 24 or len(json.dumps(candidate, ensure_ascii=True).encode()) > 64 * 1024:
            index = next((i for i, item in enumerate(candidate[:-1]) if item.get("trace_version") != VERSION), None)
            if index is None:
                # Preserve actual rejection and binding provenance before redundant snapshots.
                priority = {"reference_failure", "resolved_references", "graph_step", "graph_validation", "selection_attempt"}
                index = next((i for i, item in enumerate(candidate[:-1]) if item.get("event") not in priority), None) if event in priority else None
                if index is None:
                    target.detail_omitted += 1
                    return
            candidate.pop(index)
            target.detail_omitted += 1
        target.details[:] = candidate
    except Exception:
        target.detail_omitted += 1


def safe_observation(function):
    """Observational helper failures never change the enclosing operation."""
    from functools import wraps
    @wraps(function)
    def wrapped(*args, **kwargs):
        target = current.get()
        if target is None:
            return None
        try:
            return function(*args, **kwargs)
        except Exception:
            target.detail_omitted += 1
            return None
    return wrapped
