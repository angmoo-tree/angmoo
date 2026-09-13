"""Closed native tool selection values; no provider or LangGraph dependency."""
from copy import deepcopy
from dataclasses import dataclass, field, replace
import json

from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.retrieval_router import (
    parse_retrieval_intent_payload, retrieval_router_response_schema, ROUTER_INTENTS,
)
from app.domains.chat.contracts.workflow_recipe import workflow_recipe_for_intent
from app.domains.chat.contracts.reference_observation import reference_call, reference_inputs

TOOL_NAMES = frozenset({"CANONICAL", "GRAPH"})
CONTROL_NAMES = frozenset({"USE_CONTEXT", "REQUEST_CLARIFICATION"})
SEMANTIC_FIELDS = ("intent", "entities", "relationship", "time_scope", "aggregation", "coordination_hint")


@dataclass(frozen=True, slots=True)
class SelectionArgumentOptions:
    """Request-owned experiments; no provider or model-specific behavior."""

    code_coordination: bool = False
    positional_entity_refs: bool = False
    graph_query_contract: bool = False

    def __post_init__(self):
        if type(self.code_coordination) is not bool or type(self.positional_entity_refs) is not bool:
            raise ValueError("selection_argument_options_invalid")
        if type(self.graph_query_contract) is not bool or (self.graph_query_contract and self.positional_entity_refs):
            raise ValueError("selection_argument_options_invalid")

    @property
    def active(self):
        return self.code_coordination or self.positional_entity_refs or self.graph_query_contract

    @property
    def version(self):
        if self.graph_query_contract:
            return f"selection-args.v2.a{int(self.code_coordination)}"
        return f"selection-args.v1.a{int(self.code_coordination)}b{int(self.positional_entity_refs)}"


@dataclass(slots=True)
class SelectionValidationTrace:
    """Only closed stage/status values and applicability, never model content."""

    stages: dict = field(default_factory=lambda: dict.fromkeys(
        ("wire", "entities", "relationship", "meaning", "coordination", "agreement"), "not_evaluated"))
    applicable: dict = field(default_factory=lambda: {"entities": None, "relationship": None, "coordination": None})
    current: str = "wire"

    def step(self, stage, status):
        if stage not in self.stages or status not in {"running", "pass", "fail"}:
            raise ValueError("selection_validation_stage_invalid")
        self.stages[stage] = status
        if status == "running":
            self.current = stage

    def fail(self, code):
        # The legacy envelope also checks bound endpoints and duplicate refs.
        stage = {"relationship_unbound": "relationship", "entity_ref_invalid": "entities"}.get(code, self.current)
        self.stages[stage] = "fail"

    def snapshot(self):
        return {"stages": dict(self.stages), "applicable": dict(self.applicable)}


@dataclass(frozen=True, slots=True)
class SelectionToolCall:
    call_id: str
    name: str
    arguments_json: str
    origin: str = "model"

    def arguments(self) -> dict:
        return json.loads(self.arguments_json)


def tool_arguments_schema() -> dict:
    properties = retrieval_router_response_schema()["properties"]
    entity = properties["entities"]["items"]["properties"]
    entity["ref"].update(pattern="^[a-z][a-z0-9-]{0,63}$", maxLength=64,
                         description="Local mention alias such as entity-1. Built-in relationship endpoints responding_character/requester_character are NOT entity-list refs.")
    entity["mention"].update(minLength=1, maxLength=160)
    entity["ref"]["minLength"] = 1
    properties["intent"]["description"] = "Meaning of the whole user request. When calling both tools, use the same whole-request meaning in both calls."
    properties["relationship"]["description"] = "Null unless the request specifies a relationship meaning. Never use placeholder endpoints. Non-null endpoints must be responding_character, requester_character or a ref declared in entities."
    properties["time_scope"]["description"] = "Null when no time constraint is specified. Otherwise preserve the user's time expression; do not invent dates."
    properties["aggregation"]["description"] = "Null unless counting, comparing, ranking or another declared aggregation is requested. Do not invent an aggregation for ordinary recall."
    properties["coordination_hint"]["description"] = "Null for a single tool. For both tools supply the same supported hint and exactly the same complete semantic arguments to each call."
    return {"type": "object", "properties": {key: properties[key] for key in SEMANTIC_FIELDS},
            "required": list(SEMANTIC_FIELDS), "additionalProperties": False}


def execution_arguments_schema(*, graph_query_contract=False) -> dict:
    """ToolNode consumes the normalized internal contract, not the model schema."""
    schema = tool_arguments_schema()
    # The parser checks the fixed perspective; the internal relationship value
    # stores just its directed endpoints and dimensions (see its payload()).
    relationship = schema["properties"]["relationship"]
    del relationship["properties"]["perspective"]
    relationship["required"].remove("perspective")
    if graph_query_contract:
        from app.domains.chat.contracts.graph_query_selection import graph_queries_schema
        schema["properties"]["graph_queries"] = graph_queries_schema(internal=True)
        schema["required"].append("graph_queries")
    return schema


def model_arguments_schema(options: SelectionArgumentOptions = SelectionArgumentOptions()) -> dict:
    schema = tool_arguments_schema()
    properties = schema["properties"]
    if options.code_coordination:
        del properties["coordination_hint"]
        schema["required"].remove("coordination_hint")
    if options.positional_entity_refs:
        entity = properties["entities"]["items"]
        del entity["properties"]["ref"]
        entity["required"].remove("ref")
        properties["entities"]["description"] = (
            "Ordered person mentions and their existing roles. The first item is E1, then E2, E3, E4. "
            "Do not assign a ref field. Both retrieval calls must use the same ordered list."
        )
        relation = properties["relationship"]
        relation["description"] = (
            "Null when no relationship meaning is requested. Endpoints: SELF is the responding character; "
            "USER is the requester character; E1..E4 refer to the corresponding entities item. "
            "Only use an E number whose item exists. Preserve the requested direction."
        )
        for endpoint in ("from", "to"):
            relation["properties"][endpoint] = {"type": "string", "enum": ["SELF", "USER", "E1", "E2", "E3", "E4"]}
    if options.graph_query_contract:
        from app.domains.chat.contracts.graph_query_selection import candidate_schema
        schema = candidate_schema(schema)
    return schema


def parse_selection(text: str, calls: tuple[SelectionToolCall, ...], *, validation_step=None):
    if not calls:
        payload = json.loads(text)
        if not isinstance(payload, dict) or set(payload) != {*SEMANTIC_FIELDS, "control", "clarification_slot"}:
            raise RetrievalContractError("retrieval_router_payload_keys_invalid")
        control = payload.pop("control")
        if control not in {"CURRENT_CONTEXT", "CLARIFICATION"}:
            raise RetrievalContractError("retrieval_intent_decision_route_mismatch")
        return parse_retrieval_intent_payload({**payload, "version":"retrieval-intent.v1", "decision":control, "route":control}, validation_step=validation_step)
    if text.strip() or len(calls) > 2 or len({c.call_id for c in calls}) != len(calls):
        raise RetrievalContractError("retrieval_router_payload_keys_invalid")
    if len({c.name for c in calls}) != len(calls) or any(c.name not in TOOL_NAMES for c in calls):
        raise RetrievalContractError("retrieval_router_route_unknown")
    if any(not c.call_id or len(c.call_id) > 256 for c in calls):
        raise RetrievalContractError("retrieval_router_payload_keys_invalid")
    arguments = calls[0].arguments()
    if not isinstance(arguments, dict) or set(arguments) != set(SEMANTIC_FIELDS):
        raise RetrievalContractError("retrieval_router_payload_keys_invalid")
    if any(call.arguments() != arguments for call in calls[1:]):
        raise RetrievalContractError("retrieval_router_coordination_route_mismatch")
    return parse_retrieval_intent_payload({
        **arguments, "version": "retrieval-intent.v1", "decision": "RETRIEVAL",
        "route": "BOTH" if len(calls) == 2 else calls[0].name, "clarification_slot": None,
    }, validation_step=validation_step)


def control_arguments_schema(name: str, options: SelectionArgumentOptions = SelectionArgumentOptions()) -> dict:
    if name not in CONTROL_NAMES:
        raise ValueError("unknown_selection_control")
    schema = model_arguments_schema(options)
    if name == "REQUEST_CLARIFICATION":
        schema["properties"]["clarification_slot"] = retrieval_router_response_schema()["properties"]["clarification_slot"]
        schema["required"].append("clarification_slot")
    return schema


def parse_control_selection(
    text: str, calls: tuple[SelectionToolCall, ...], *,
    options: SelectionArgumentOptions = SelectionArgumentOptions(),
    trace: SelectionValidationTrace | None = None,
):
    """Every outcome is native; retrieval and controls cannot be mixed."""
    trace = trace or SelectionValidationTrace()
    trace.step("wire", "running")
    if text.strip() or not calls or len(calls) > 2:
        raise RetrievalContractError("retrieval_router_payload_keys_invalid")
    if any(not call.call_id or len(call.call_id) > 256 for call in calls):
        raise RetrievalContractError("retrieval_router_payload_keys_invalid")
    if len({call.call_id for call in calls}) != len(calls) or len({call.name for call in calls}) != len(calls):
        raise RetrievalContractError("retrieval_router_payload_keys_invalid")
    if any(call.name not in TOOL_NAMES | CONTROL_NAMES for call in calls):
        raise RetrievalContractError("retrieval_router_route_unknown")
    if any(call.name in CONTROL_NAMES for call in calls) and len(calls) != 1:
        raise RetrievalContractError("retrieval_router_payload_keys_invalid")
    payloads = [call.arguments() for call in calls]
    for call, payload in zip(calls, payloads, strict=True):
        expected = set(SEMANTIC_FIELDS) - ({"coordination_hint"} if options.code_coordination else set())
        if options.graph_query_contract:
            expected.add("graph_queries")
        if call.name == "REQUEST_CLARIFICATION":
            expected.add("clarification_slot")
        if not isinstance(payload, dict) or set(payload) != expected:
            raise RetrievalContractError("retrieval_router_payload_keys_invalid")
    trace.applicable.update(
        entities=any(bool(p["entities"]) for p in payloads),
        relationship=any(p["relationship"] is not None for p in payloads),
        coordination=len(calls) == 2,
    )
    trace.step("wire", "pass")
    normalized_items = []
    graph_queries_items = []
    for ordinal, (call, payload) in enumerate(zip(calls, payloads, strict=True), 1):
        reference_call(ordinal)
        reference_inputs(payload, "received_arguments")
        if options.graph_query_contract:
            from app.domains.chat.contracts.graph_query_selection import normalize_candidate
            payload, queries = normalize_candidate(payload)
            graph_queries_items.append(queries)
        arguments = _normalize_model_arguments(payload, both=len(calls) == 2, options=options, trace=trace)
        reference_inputs(arguments, "normalized_arguments")
        normalized_items.append(replace(call, arguments_json=json.dumps(arguments, ensure_ascii=False, sort_keys=True)))
    normalized = tuple(normalized_items)
    reference_call(1)  # Identical whole-request arguments are validated once below.
    trace.step("agreement", "running")
    if len(normalized) == 2 and normalized[0].arguments() != normalized[1].arguments():
        raise RetrievalContractError("retrieval_router_coordination_route_mismatch")
    if len(graph_queries_items) == 2 and graph_queries_items[0] != graph_queries_items[1]:
        raise RetrievalContractError("retrieval_router_coordination_route_mismatch")
    trace.step("agreement", "pass")
    calls = normalized
    if any(call.name in CONTROL_NAMES for call in calls):
        if len(calls) != 1:
            raise RetrievalContractError("retrieval_router_payload_keys_invalid")
        call = calls[0]
        payload = call.arguments()
        expected = set(SEMANTIC_FIELDS)
        clarify = call.name == "REQUEST_CLARIFICATION"
        if clarify:
            expected.add("clarification_slot")
        if not isinstance(payload, dict) or set(payload) != expected:
            raise RetrievalContractError("retrieval_router_payload_keys_invalid")
        intent = parse_selection(json.dumps({
            **payload, "control": "CLARIFICATION" if clarify else "CURRENT_CONTEXT",
            "clarification_slot": payload.get("clarification_slot"),
        }), (), validation_step=trace.step)
    else:
        intent = parse_selection(text, calls, validation_step=trace.step)
    if options.graph_query_contract:
        queries = graph_queries_items[0]
        if any(c.name == "GRAPH" for c in calls) and not queries:
            raise RetrievalContractError("graph_query_count_invalid")
        intent = replace(intent, version="retrieval-intent.v2", graph_queries=queries)
    reference_inputs(intent.payload(), "validated_intent")
    return replace(intent, coordination_source="code") if options.code_coordination else intent


def _normalize_model_arguments(payload, *, both, options, trace):
    arguments = deepcopy(payload)
    if options.positional_entity_refs:
        trace.step("entities", "running")
        entities = arguments["entities"]
        if not isinstance(entities, list) or len(entities) > 4:
            raise RetrievalContractError("retrieval_router_entities_invalid")
        for index, entity in enumerate(entities, 1):
            if not isinstance(entity, dict) or set(entity) != {"mention", "role"}:
                raise RetrievalContractError("retrieval_router_entity_keys_invalid")
            entity["ref"] = f"entity-{index}"
        trace.step("entities", "pass")
        relationship = arguments["relationship"]
        if relationship is not None:
            trace.step("relationship", "running")
            if not isinstance(relationship, dict):
                raise RetrievalContractError("retrieval_router_relationship_invalid")
            endpoints = {"SELF": "responding_character", "USER": "requester_character"}
            endpoints.update({f"E{i}": f"entity-{i}" for i in range(1, len(entities) + 1)})
            for key in ("from", "to"):
                value = relationship.get(key)
                if not isinstance(value, str) or value not in endpoints:
                    raise RetrievalContractError("retrieval_intent_relationship_unbound")
                relationship[key] = endpoints[value]
            trace.step("relationship", "pass")
    if options.code_coordination:
        trace.step("coordination", "running")
        meaning = arguments["intent"]
        if not isinstance(meaning, str) or meaning not in ROUTER_INTENTS:
            raise RetrievalContractError("retrieval_router_intent_unknown")
        arguments["coordination_hint"] = workflow_recipe_for_intent(meaning).recipe.value if both else None
        trace.step("coordination", "pass")
    return arguments


def effective_calls(request_id: str, intent, proposed: tuple[SelectionToolCall, ...]):
    names = TOOL_NAMES if intent.route.value == "BOTH" else ({intent.route.value} & TOOL_NAMES)
    arguments = {key: intent.payload()[key] for key in SEMANTIC_FIELDS}
    if intent.version == "retrieval-intent.v2":
        arguments["graph_queries"] = [q.payload() for q in intent.graph_queries]
    by_name = {call.name: call for call in proposed}
    return tuple(SelectionToolCall(
        call_id=by_name[name].call_id if name in by_name else f"{request_id}:guard:{name}",
        name=name, arguments_json=json.dumps(arguments, sort_keys=True, ensure_ascii=False),
        origin=by_name[name].origin if name in by_name else "code_guard",
    ) for name in sorted(names))
