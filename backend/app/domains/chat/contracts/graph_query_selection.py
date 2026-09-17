"""Typed person selectors and graph meaning; all aliases are code-owned."""
from copy import deepcopy

from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.relationships.contracts.graph_requirements import GraphQueryRequirement, validate_graph_queries


def person_selector_schema():
    return {"type": "object", "properties": {
        "kind": {"type": "string", "enum": ["responding_character", "requester_character", "mention"]},
        "index": {"type": ["integer", "null"], "minimum": 1, "maximum": 4},
    }, "required": ["kind", "index"], "additionalProperties": False,
        "description": "Built-in characters use index=null. mention uses the 1-based entities position. Never declare a built-in in entities."}


def graph_queries_schema(*, internal=False):
    properties = {"kind": {"type": "string", "enum": ["pair", "collection", "shared", "path"]},
                  "direction": {"type": "string", "enum": ["outgoing", "incoming", "bidirectional", "either"]},
                  "result_of": {"type": ["integer", "null"], "minimum": 1, "maximum": 2}}
    if internal:
        properties["target_ref"] = {"type": ["string", "null"]}
    else:
        properties["target"] = {**person_selector_schema(), "type": ["object", "null"]}
    return {"type": "array", "maxItems": 3, "items": {
        "type": "object", "properties": properties, "required": list(properties), "additionalProperties": False},
        "description": "Graph requirements in order; [] when no graph facts are requested. Center is always the responding character. pair needs a target, collection has no target, shared/path need a target. A later query may use result_of=earlier requirement number instead of target. bidirectional means two separate pair directions; either is only for shared/path. Do not invent an unknown person for a collection."}


def candidate_schema(schema):
    schema = deepcopy(schema)
    entity = schema["properties"]["entities"]["items"]
    del entity["properties"]["ref"]
    entity["required"].remove("ref")
    schema["properties"]["entities"]["description"] = "Ordered non-built-in person mentions and roles only; no ref IDs."
    relationship = schema["properties"]["relationship"]
    for key in ("from", "to"):
        relationship["properties"][key] = person_selector_schema()
    relationship["description"] = "Optional directed fact meaning for canonical records. Use typed person selectors; never force graph collections or bidirectional requirements into a single directed pair. Graph requirements belong in graph_queries."
    schema["properties"]["graph_queries"] = graph_queries_schema()
    schema["required"].append("graph_queries")
    return schema


def _selector(value, count):
    if not isinstance(value, dict) or set(value) != {"kind", "index"}:
        raise RetrievalContractError("graph_selection_person_invalid")
    kind, index = value["kind"], value["index"]
    if kind in {"responding_character", "requester_character"} and index is None:
        return kind
    if kind == "mention" and type(index) is int and 1 <= index <= count:
        return f"entity-{index}"
    raise RetrievalContractError("graph_selection_person_unbound")


def normalize_candidate(payload):
    arguments = deepcopy(payload)
    entities = arguments.get("entities")
    if not isinstance(entities, list) or len(entities) > 4:
        raise RetrievalContractError("retrieval_router_entities_invalid")
    for index, entity in enumerate(entities, 1):
        if not isinstance(entity, dict) or set(entity) != {"mention", "role"}:
            raise RetrievalContractError("retrieval_router_entity_keys_invalid")
        entity["ref"] = f"entity-{index}"
    relationship = arguments.get("relationship")
    if relationship is not None:
        if not isinstance(relationship, dict):
            raise RetrievalContractError("retrieval_router_relationship_invalid")
        for endpoint in ("from", "to"):
            relationship[endpoint] = _selector(relationship.get(endpoint), len(entities))
    raw = arguments.pop("graph_queries")
    if not isinstance(raw, list) or len(raw) > 3:
        raise RetrievalContractError("graph_query_count_invalid")
    queries = []
    for value in raw:
        if not isinstance(value, dict) or set(value) != {"kind", "direction", "target", "result_of"}:
            raise RetrievalContractError("graph_query_keys_invalid")
        target = None if value["target"] is None else _selector(value["target"], len(entities))
        if target == "responding_character":
            raise RetrievalContractError("graph_query_self_target_invalid")
        if target == "requester_character":
            target = "builtin-requester"
        queries.append(GraphQueryRequirement(value["kind"], value["direction"], target, value["result_of"]))
    if queries:
        validate_graph_queries(queries, {e["ref"] for e in entities} | {"builtin-requester"})
    return arguments, tuple(queries)
