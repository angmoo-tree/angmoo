"""Request-local reference provenance; never validate, resolve, or repair input."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from app.contracts.decision_observation import alias, closed, emit, safe_observation, shape
from app.contracts.retrieval_observation import current

_BUILTINS = {"responding_character", "requester_character"}
_ROLES = {"actor", "target", "counterpart", "subject", "mentioned_third_party"}
_FIELDS = {"entity_ref": "entities.ref", "relationship_from": "relationship.from", "relationship_to": "relationship.to"}


@dataclass
class _Attempt:
    phase: str
    call: int = 1
    entity_index: int = 0
    received: dict = field(default_factory=dict)


_active = ContextVar("chat_reference_observation", default=None)


@contextmanager
def reference_attempt(phase):
    token = _active.set(_Attempt(phase) if current.get() is not None else None)
    try:
        yield
    finally:
        _active.reset(token)


def _ref(value):
    return value if type(value) is str and value in _BUILTINS else alias("ref", value)


def _features(value):
    result = {"value_type": shape(value)}
    if type(value) is str:
        sample = value[:161]
        result.update(value_length=min(len(value), 1_000_000_000),
                      features_complete="yes" if len(value) <= 161 else "no",
                      first_lower="yes" if value and "a" <= value[0] <= "z" else "no",
                      has_uppercase="yes" if any("A" <= c <= "Z" for c in sample) else "no",
                      has_underscore="yes" if "_" in sample else "no",
                      has_space="yes" if any(c.isspace() for c in sample) else "no",
                      has_non_ascii="yes" if any(ord(c) > 127 for c in sample) else "no",
                      has_other="yes" if any(not ("a" <= c <= "z" or "0" <= c <= "9" or c == "-") for c in sample) else "no")
    return result


@safe_observation
def reference_entity(index):
    if _active.get() is not None:
        _active.get().entity_index = index


@safe_observation
def reference_call(ordinal):
    if _active.get() is not None:
        _active.get().call = ordinal
        _active.get().received.clear()


@safe_observation
def reference_value(field_name, value):
    """Remember only bounded, already-sanitized pre-string-normalization shape."""
    state = _active.get()
    if state is None or field_name not in _FIELDS:
        return
    observation = current.get()
    if observation.detailed:
        state.received[field_name] = {**_features(value), "ref_alias": _ref(value)}


@safe_observation
def reference_failure(field_name, value, *, rule, reason, related=None, declared=None):
    state = _active.get()
    if state is None:
        return
    path = _FIELDS.get(field_name, "relationship" if field_name == "relationship" else "entities.ref")
    basic = {"status": "rejected", "field_path": path, "failure_reason": reason,
             "applied_rule": rule, "call": state.call}
    if path == "entities.ref":
        basic["entity_index"] = state.entity_index
    values = {**basic, "input_stage": "normalized_arguments"}
    if current.get().detailed:
        values.update(_features(value), ref_alias=_ref(value))
        received = state.received.get(field_name)
        if received is not None:
            values.update({"received_" + key: item for key, item in received.items()})
            comparable = type(value) is str and bool(value) and len(value) <= 160
            values["normalization_changed"] = ("no" if received["ref_alias"] == values["ref_alias"] else "yes") if comparable and received["ref_alias"] not in {"unresolved", "alias_limit"} else "unknown"
        if related is not None:
            values.update(to_ref=_ref(related), same_endpoint="yes" if value == related else "no")
        if declared is not None:
            values["from_resolution"] = "builtin" if value in _BUILTINS else "declared" if value in declared else "undeclared"
            if related is not None:
                values["to_resolution"] = "builtin" if related in _BUILTINS else "declared" if related in declared else "undeclared"
    emit("reference_failure", axis="supervisor", phase=state.phase, basic=basic, **values)


@safe_observation
def reference_inputs(arguments, stage):
    state = _active.get()
    if state is None or not current.get().detailed or type(arguments) is not dict:
        return
    row = {"call": state.call, "input_stage": stage}
    entities = arguments.get("entities")
    if type(entities) is list:
        row["entity_count"] = len(entities)
        for i, entity in enumerate(entities[:4], 1):
            if type(entity) is dict:
                row[f"entity_{i}_ref"] = alias("ref", entity.get("ref"))
                row[f"entity_{i}_role"] = closed(entity.get("role"), _ROLES)
    relation = arguments.get("relationship")
    if type(relation) is dict:
        row.update(from_ref=_ref(relation.get("from")), to_ref=_ref(relation.get("to")))
    emit("reference_inputs", axis="supervisor", phase=state.phase, **row)


@safe_observation
def resolved_references(intent, resolutions, *, phase, subject, bindings=(), direction=None):
    if not current.get().detailed:
        return
    row = {"input_stage": "resolved_binding" if direction is not None else "entity_resolution",
           "applied_rule": "unique_safe_binding.v1", "entity_count": len(intent.entities)}
    by_ref = {item.ref: item for item in resolutions}
    bound = {item.ref: item.world_character_id for item in bindings}
    def identity(value):
        return "responding_character" if value == subject else alias("identity", value) if value is not None else "unresolved"
    for i, entity in enumerate(intent.entities[:4], 1):
        row[f"entity_{i}_ref"] = alias("ref", entity.ref)
        row[f"entity_{i}_role"] = closed(entity.role, _ROLES)
        resolution = by_ref.get(entity.ref)
        candidates = () if resolution is None else resolution.candidates
        row[f"entity_{i}_candidates"] = len(candidates)
        row[f"entity_{i}_safe"] = sum(bool(c.safe_for_clarification) for c in candidates)
        row[f"entity_{i}_identity"] = identity(bound.get(entity.ref)) if direction is not None else "not_evaluated"
    if intent.relationship is not None:
        row.update(from_ref=_ref(intent.relationship.from_ref), to_ref=_ref(intent.relationship.to_ref))
    if direction is not None:
        row.update(upstream_from=identity(direction[0]), upstream_to=identity(direction[1]),
                   status=closed(direction[2], {"resolved", "ambiguous", "not_requested"}))
    emit("resolved_references", axis="supervisor", phase=phase, **row)
