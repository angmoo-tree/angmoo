"""Safe observations of selection contracts; never decide or repair a selection."""
from app.contracts.decision_observation import alias, closed, emit, safe_observation, shape
from app.domains.chat.contracts.retrieval_router import (
    normalize_router_validation_code, ROUTER_INTENTS, ROUTER_ENTITY_ROLES,
    ROUTER_RELATIONSHIP_DIMENSIONS, ROUTER_RELATIONSHIP_POLARITIES,
    ROUTER_AGGREGATION_TARGETS,
)

_FIELDS = {"intent", "entities", "relationship", "time_scope", "aggregation", "coordination_hint", "clarification_slot", "graph_queries"}
_REL_FIELDS = {"perspective", "from", "to", "dimension", "requested_polarity"}
_TOOLS = {"CANONICAL", "GRAPH", "USE_CONTEXT", "REQUEST_CLARIFICATION"}
_BUILTINS = {"responding_character", "requester_character"}
FINISH_REASONS = {"STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "LANGUAGE", "OTHER", "BLOCKLIST",
    "PROHIBITED_CONTENT", "SPII", "MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL", "TOO_MANY_TOOL_CALLS",
    "MISSING_THOUGHT_SIGNATURE", "MALFORMED_RESPONSE", "FINISH_REASON_UNSPECIFIED",
    "stop", "length", "tool_calls", "content_filter", "end_turn", "tool_use", "max_tokens", "stop_sequence", "pause_turn", "refusal"}
_PATHS = {"retrieval_router_perspective_invalid": "relationship.perspective",
    "retrieval_router_relationship_from_invalid": "relationship.from",
    "retrieval_router_relationship_to_invalid": "relationship.to",
    "retrieval_router_relationship_dimension_invalid": "relationship.dimension",
    "retrieval_router_relationship_polarity_invalid": "relationship.requested_polarity",
    "retrieval_router_relationship_invalid": "relationship",
    "retrieval_router_relationship_keys_invalid": "relationship",
    "retrieval_intent_relationship_ref_invalid": "relationship",
    "retrieval_intent_relationship_self_invalid": "relationship",
    "retrieval_intent_relationship_unbound": "relationship"}


def _code(error):
    seen = set()
    for _ in range(6):
        if error is None or id(error) in seen:
            break
        seen.add(id(error))
        raw = str(error)
        if normalize_router_validation_code(raw) != "router_validation_unknown":
            return raw
        error = error.__cause__ or error.__context__
    return "unknown"


def _endpoint(value, refs):
    if type(value) is not str:
        return "invalid_type", "unresolved"
    if value in _BUILTINS:
        return value, "builtin"
    if value in refs:
        return alias("ref", value), "declared"
    return alias("ref", value), "undeclared"


@safe_observation
def selection_attempt(request, response, *, error=None, physical_attempts=0,
                      model="unknown", provider="unknown", thinking_level="unknown", max_output_tokens=0, validation_trace=None):
    phase = "repair" if request.repair_diagnostic is not None else "first"
    code = _code(error) if error is not None else "valid"
    normalized = normalize_router_validation_code(code) if error is not None else "valid"
    calls = getattr(response, "tool_calls", ()) if response is not None else ()
    reason = closed(getattr(response, "finish_reason", None), FINISH_REASONS)
    response_state = "not_received" if response is None else "received"
    usage = getattr(response, "usage", None)
    metrics = {}
    if type(usage) is dict:
        for source, target in (("prompt_token_count", "input_tokens"), ("candidates_token_count", "output_tokens"),
                               ("thoughts_token_count", "thought_tokens"), ("total_token_count", "total_tokens")):
            if type(usage.get(source)) is int and usage[source] >= 0:
                metrics[target] = usage[source]
    stages = {}
    if validation_trace is not None:
        for key in ("wire", "entities", "relationship", "meaning", "coordination", "agreement"):
            stages[key + "_stage"] = closed(validation_trace.stages.get(key), {"running", "pass", "fail", "not_evaluated"})
    basic = {"status": "rejected" if error is not None else "validated", "validation_code": code,
             "field_path": _PATHS.get(code, "not_identified"), "finish_reason": reason,
             "response_state": response_state, "response_observed": response is not None,
             "tool_count": len(calls), "response_chars": len(getattr(response, "text", "")),
             "physical_attempts": physical_attempts, "max_output_tokens": max_output_tokens,
             "timeout_seconds": 30, "provider": provider, "model": model, "thinking_level": thinking_level, **metrics}
    emit("selection_attempt", axis="supervisor", phase=phase, basic=basic,
         **{k: v for k, v in basic.items() if k != "response_observed"},
         normalized_code=normalized, repair_code=(request.repair_diagnostic if normalize_router_validation_code(request.repair_diagnostic) != "router_validation_unknown" else "unknown")
         if request.repair_diagnostic is not None else "none",
         repair_rule="selection_code_only.v1" if request.repair_diagnostic is not None else "none",
         expected_values_supplied="no", response_observed="yes" if response else "no",
         usage_observed="yes" if metrics else "not_reported", dispatch_complete="yes" if response else "unknown", **stages)
    for ordinal, call in enumerate(calls[:2], 1):
        args = call.arguments
        if type(args) is not dict:
            emit("selection_fields", axis="supervisor", phase=phase, call=ordinal, shape_check=shape(args))
            continue
        entities = args.get("entities")
        refs = {item["ref"] for item in entities[:4] if type(item) is dict and type(item.get("ref")) is str} if type(entities) is list else set()
        row = {"call": ordinal, "function": closed(call.name, _TOOLS), "shape_check": "diagnostic_shape_only",
               "field_path": _PATHS.get(code, "not_identified"), "validation_code": code,
               "intent": closed(args.get("intent"), ROUTER_INTENTS),
               "entities_state": shape(entities, present="entities" in args),
               "relationship_state": shape(args.get("relationship"), present="relationship" in args),
               "aggregation_state": shape(args.get("aggregation"), present="aggregation" in args),
               "time_scope_state": shape(args.get("time_scope"), present="time_scope" in args),
               "coordination_state": shape(args.get("coordination_hint"), present="coordination_hint" in args),
               "extra_keys": len(set(args) - _FIELDS)}
        if type(entities) is list:
            row["entity_count"] = len(entities)
            for i, entity in enumerate(entities[:4], 1):
                if type(entity) is dict:
                    row[f"entity_{i}_ref"] = alias("ref", entity.get("ref"))
                    row[f"entity_{i}_role"] = closed(entity.get("role"), ROUTER_ENTITY_ROLES)
        relation = args.get("relationship")
        if type(relation) is dict:
            row["missing_keys"] = len(_REL_FIELDS - set(relation))
            row["extra_keys"] += len(set(relation) - _REL_FIELDS)
            for source, target in (("perspective", "perspective_state"), ("from", "from_state"), ("to", "to_state"),
                                   ("dimension", "dimension_state"), ("requested_polarity", "polarity_state")):
                row[target] = shape(relation.get(source), present=source in relation)
            row["from_ref"], row["from_resolution"] = _endpoint(relation.get("from"), refs)
            row["to_ref"], row["to_resolution"] = _endpoint(relation.get("to"), refs)
            row["perspective"] = closed(relation.get("perspective"), {"responding_character"})
            row["dimension"] = closed(relation.get("dimension"), ROUTER_RELATIONSHIP_DIMENSIONS, absent="null")
            row["polarity"] = closed(relation.get("requested_polarity"), ROUTER_RELATIONSHIP_POLARITIES, absent="null")
        aggregation = args.get("aggregation")
        if type(aggregation) is dict:
            row["aggregation_kind"] = closed(aggregation.get("kind"), {"count", "rank", "compare", "group"})
            row["aggregation_target"] = closed(aggregation.get("target_role"), ROUTER_AGGREGATION_TARGETS)
        emit("selection_fields", axis="supervisor", phase=phase, **row)
