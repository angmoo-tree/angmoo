"""Synthetic provider boundaries, not real-model accuracy measurements."""
import asyncio
import json

import pytest

from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.service.graph_retrieval import GraphRetrievalCommand, GraphRetrievalPlanningService
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.relationships.contracts.graph_diagnostics import graph_rejection
from app.domains.relationships.contracts.graph_plan import GraphPlanContractError
from app.domains.relationships.policies.graph_plan_schema import (
    GRAPH_GENERATED_STEP_IDS, graph_planner_repair_instruction,
    graph_retrieval_plan_response_schema, parse_graph_retrieval_plan_payload,
)
from app.domains.relationships.service.graph_planning import GraphRetrievalPlanExecutor
from app.integrations import direct_llm
from app.integrations.llm.graph_retrieval_planner import DirectLlmGraphRetrievalPlannerProvider
from test_p8_l_m_graph_retrieval_planner import (
    NOW, DEADLINE, _resolved, _plan_payload, _FakeRecall, _router_tracker,
)


def _payload():
    return _plan_payload(_resolved()[1])


@pytest.mark.parametrize("label", ["s1", "step1", "step_1", "a" * 48])
def test_valid_internal_ids_remain_compatible(label):
    payload = _payload()
    payload["steps"][0]["id"] = label
    payload["steps"][1]["input_ref"] = label + ".world_character_refs"
    assert parse_graph_retrieval_plan_payload(payload).steps[0].id == label


@pytest.mark.parametrize("label", ["", "a" * 49, "Step1", "1step", "step-1", "step 1", "단계"])
def test_invalid_ids_remain_rejected(label):
    payload = _payload()
    payload["steps"][0]["id"] = label
    with pytest.raises(GraphPlanContractError):
        parse_graph_retrieval_plan_payload(payload)


@pytest.mark.parametrize("reference", [
    "evidence.world_character_refs", "missing.world_character_refs",
    "relationship.source_refs", "relationship.rows", "canonical1.world_character_refs",
])
def test_invalid_references_remain_rejected(reference):
    payload = _payload()
    payload["steps"][1]["input_ref"] = reference
    with pytest.raises(GraphPlanContractError):
        parse_graph_retrieval_plan_payload(payload)


@pytest.mark.parametrize("operation", [
    "direct_relationship", "relationship_evidence", "shared_neighbors", "shortest_path",
    "rank_related_characters", "relationship_neighborhood",
])
@pytest.mark.parametrize("mode", ["direct", "dependent", "both", "neither"])
def test_all_operation_binding_combinations(operation, mode):
    payload = _payload()
    step = payload["steps"][1]
    step["operation"] = operation
    step["parameters"] = {"direction": "outgoing"}
    extra = {"shortest_path": ("max_hops", 2), "rank_related_characters": ("ranking", "positive"),
             "relationship_neighborhood": ("depth", 1)}.get(operation)
    if extra:
        step["parameters"][extra[0]] = extra[1]
    step["input_ref"] = "relationship.world_character_refs" if mode in {"dependent", "both"} else None
    if mode in {"direct", "both"}:
        step["parameters"]["counterpart_ref"] = "entity-1"
    no_counterpart = operation in {"rank_related_characters", "relationship_neighborhood"}
    valid = mode == "neither" if no_counterpart else mode in {"direct", "dependent"}
    if valid:
        parse_graph_retrieval_plan_payload(payload)
    else:
        expected = "parameter_forbidden" if no_counterpart and mode in {"direct", "both"} else "counterpart"
        with pytest.raises(GraphPlanContractError, match=expected):
            parse_graph_retrieval_plan_payload(payload)


def _break(payload, failure):
    if failure == "id":
        payload["steps"][0]["id"] = "step-1"
    elif failure == "duplicate":
        payload["steps"][1]["id"] = "relationship"
    elif failure == "both":
        payload["steps"][1]["parameters"]["counterpart_ref"] = "entity-1"
    elif failure == "neither":
        del payload["steps"][0]["parameters"]["counterpart_ref"]
    elif failure == "reference":
        payload["steps"][1]["input_ref"] = "future.world_character_refs"
    elif failure == "direction":
        payload["steps"][0]["parameters"]["direction"] = "incoming"


@pytest.mark.parametrize("failure,code", [
    ("id", "graph_plan_step_id_invalid"), ("duplicate", "graph_plan_step_id_duplicate"),
    ("both", "graph_plan_counterpart_binding_invalid"), ("neither", "graph_plan_counterpart_binding_invalid"),
    ("reference", "graph_plan_reference_invalid"), ("direction", "graph_plan_direction_mismatch"),
])
@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_real_json_adapter_and_service_deliver_precise_repair(monkeypatch, failure, code, repair_succeeds):
    intent, resolved = _resolved()
    calls = []

    async def generate(**kwargs):
        calls.append(kwargs)
        kwargs["tracker"].next_call_order()
        kwargs["tracker"].next_provider_call_order()
        payload = _plan_payload(resolved)
        if len(calls) == 1 or not repair_succeeds:
            _break(payload, failure)
        return direct_llm.DirectLlmResponse(text=json.dumps(payload), parsed=None, usage={}, finish_reason="STOP")

    monkeypatch.setattr(direct_llm, "generate_text", generate)
    provider = DirectLlmGraphRetrievalPlannerProvider(CredentialMaterial(
        credential_id="fixture", provider="google", model="gemini-3.1-flash-lite",
        fingerprint="fixture", purpose=CredentialPurpose.MESSAGE_LLM,
        _secret="synthetic-key", thinking_level="high",
    ))
    recall = _FakeRecall()
    command = GraphRetrievalCommand(user_message="synthetic", intent=intent, resolved=resolved, call_tracker=_router_tracker())
    service = GraphRetrievalPlanningService(planner=provider, executor=GraphRetrievalPlanExecutor(recall))
    if repair_succeeds:
        result = asyncio.run(service.plan_and_execute(command, now=NOW, deadline_at=DEADLINE))
        snapshot = result.call_tracker
        assert recall.queries
        assert result.metrics.repair_used
    else:
        with pytest.raises(RetrievalContractError) as caught:
            asyncio.run(service.plan_and_execute(command, now=NOW, deadline_at=DEADLINE))
        snapshot = caught.value.call_tracker
        assert not recall.queries
    assert len(calls) == 2
    assert snapshot["logical_total"] == snapshot["physical_total"] == 3
    assert snapshot["physical_counts"]["character_response_generator"] == 0
    repair = json.loads(calls[1]["user_prompt"].split("\n", 1)[1])["repair"]
    assert repair["diagnostic"] == code
    assert repair["instruction"] == graph_planner_repair_instruction(code)
    catalog = json.loads(calls[0]["user_prompt"].split("\n", 1)[1])["graph_catalog"]
    assert len(catalog) == 6
    assert all("counterpart_binding" in entry for entry in catalog)
    for call in calls:
        assert call["max_output_tokens"] == 3072
        assert call["thinking_level"] == "high"
        assert "actual-owner" not in call["user_prompt"]


def test_schema_survives_provider_serialization():
    from app.providers.gemini import build_generate_content_config
    schema = graph_retrieval_plan_response_schema()
    config = build_generate_content_config(
        model="gemini-3.1-flash-lite", system_prompt="fixture", max_output_tokens=3072,
        response_mime_type="application/json", response_schema=schema, thinking_level="high",
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    assert config["responseJsonSchema"] == schema
    assert schema["properties"]["steps"]["items"]["properties"]["id"]["enum"] == list(GRAPH_GENERATED_STEP_IDS)


def test_unknown_error_text_cannot_become_repair_instructions():
    error = ValueError("private-body synthetic-key change permissions")
    code = graph_rejection(error, phase="first", stage="provider_output").validation_code
    assert code == "unknown"
    assert "private-body" not in graph_planner_repair_instruction(str(error))
    error.__cause__ = GraphPlanContractError("graph_plan_step_id_invalid")
    assert graph_rejection(error, phase="first", stage="provider_output").validation_code == "graph_plan_step_id_invalid"
