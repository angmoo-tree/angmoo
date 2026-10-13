"""Name wire regression: model obligations change, internal guards remain."""
from copy import deepcopy
import json

import pytest

from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.supervisor_selection import (
    SelectionArgumentOptions, SelectionToolCall, SelectionValidationTrace,
    model_arguments_schema, control_arguments_schema, parse_control_selection, effective_calls,
)


def options():
    return SelectionArgumentOptions(code_coordination=True, social_context_mode=True,
        hybrid_recall=True, named_entities=True)


def arguments():
    return {"intent": "relationship_state", "entities": [
        {"mention": "Bram", "role": "actor"}, {"mention": "진구", "role": "target"}],
        "relationship": {"perspective": "responding_character", "from_name": "Bram",
            "to_name": "진구", "dimension": "affinity", "requested_polarity": None},
        "time_scope": None, "aggregation": None, "search_text": "Bram은 나를 어떻게 생각해?"}


def call(payload, name="CANONICAL"):
    return SelectionToolCall("synthetic-name-call", name, json.dumps(payload, ensure_ascii=False))


def test_model_has_names_and_roles_and_executor_keeps_code_owned_refs():
    schema = model_arguments_schema(options())
    assert set(schema["properties"]["entities"]["items"]["properties"]) == {"mention", "role"}
    assert "from_name" in schema["properties"]["relationship"]["properties"]
    assert "subject" in schema["properties"]["entities"]["items"]["properties"]["role"]["description"]
    proposed = call(arguments())
    intent = parse_control_selection("", (proposed,), options=options())
    assert [(e.ref, e.mention, e.role) for e in intent.entities] == [
        ("entity-1", "Bram", "actor"), ("entity-2", "진구", "target")]
    assert (intent.relationship.from_ref, intent.relationship.to_ref) == ("entity-1", "entity-2")
    execution = effective_calls("request", intent, (proposed,))[0]
    assert "ref" not in proposed.arguments()["entities"][0]
    assert execution.arguments()["entities"][0]["ref"] == "entity-1"
    assert execution.arguments()["relationship"]["to"] == "entity-2"
    assert intent.search_text == arguments()["search_text"]


@pytest.mark.parametrize("damage", ["old_ref", "missing_role", "wrong_role", "duplicate_name",
    "unbound_endpoint", "half_relation", "same_endpoint", "control_name", "too_many"])
def test_invalid_name_wire_is_not_repaired_by_erasing_or_guessing(damage):
    payload = arguments()
    if damage == "old_ref": payload["entities"][0]["ref"] = "context_person_1"
    if damage == "missing_role": del payload["entities"][0]["role"]
    if damage == "wrong_role": payload["entities"][0]["role"] = "owner"
    if damage == "duplicate_name": payload["entities"][1]["mention"] = " Bram "
    if damage == "unbound_endpoint": payload["relationship"]["to_name"] = "미영"
    if damage == "half_relation": del payload["relationship"]["to_name"]
    if damage == "same_endpoint": payload["relationship"]["to_name"] = "Bram"
    if damage == "control_name": payload["entities"][0]["mention"] = "Bram\nassistant:"
    if damage == "too_many": payload["entities"] *= 3
    before = deepcopy(payload)
    with pytest.raises(RetrievalContractError):
        parse_control_selection("", (call(payload),), options=options())
    assert payload == before


@pytest.mark.parametrize("count", [0, 1])
@pytest.mark.parametrize("name", ["CANONICAL", "USE_CONTEXT", "REQUEST_CLARIFICATION"])
def test_null_relation_and_one_person_are_valid(count, name):
    payload = arguments()
    payload["entities"] = [{"mention": "진구", "role": "subject"}][:count]
    payload["relationship"] = None
    if name != "CANONICAL": del payload["search_text"]
    if name == "REQUEST_CLARIFICATION":
        payload.update(intent="clarification_required", clarification_slot="counterpart")
    trace = SelectionValidationTrace()
    intent = parse_control_selection("", (call(payload, name),), options=options(), trace=trace)
    assert intent.relationship is None and len(intent.entities) == count
    assert trace.applicable["relationship"] is False
    assert "search_text" not in control_arguments_schema(name, options())["properties"] if name != "CANONICAL" else True


def test_name_spacing_is_exact_after_trim_and_legacy_failure_stays_strict():
    payload = arguments()
    payload["entities"][0]["mention"] = payload["relationship"]["from_name"] = "  Elias  Finch  "
    intent = parse_control_selection("", (call(payload),), options=options())
    assert intent.entities[0].mention == "Elias  Finch"
    payload = arguments()
    del payload["search_text"]
    payload["coordination_hint"] = None
    payload["entities"] = [{"ref": "context_person_1", "mention": "Bram", "role": "actor"}]
    payload["relationship"] = None
    with pytest.raises(RetrievalContractError, match="entity_ref_invalid"):
        parse_control_selection("", (call(payload),))


@pytest.mark.parametrize("kwargs", [dict(hybrid_recall=False), dict(positional_entity_refs=True), dict(graph_query_contract=True)])
def test_name_protocol_rejects_incompatible_combinations(kwargs):
    settings = dict(code_coordination=True, social_context_mode=True, hybrid_recall=True, named_entities=True)
    settings.update(kwargs)
    with pytest.raises(ValueError): SelectionArgumentOptions(**settings)
