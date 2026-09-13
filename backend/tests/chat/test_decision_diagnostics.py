"""Diagnostic evidence and invariance, with no real provider or private database."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from app.contracts.decision_observation import emit, safe_observation
from app.contracts.retrieval_observation import Observation, current
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest
from app.domains.chat.service.graph_retrieval import GraphRetrievalCommand, GraphRetrievalPlanningService
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.relationships.service.graph_planning import GraphRetrievalPlanExecutor
from app.integrations import direct_llm
from app.integrations.llm.graph_retrieval_planner import DirectLlmGraphRetrievalPlannerProvider
from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider
from app.providers.contracts import ProviderToolCall
from test_p8_l_m_graph_retrieval_planner import NOW, DEADLINE, _resolved, _plan_payload, _FakeRecall, _router_tracker


@contextmanager
def recording(enabled):
    observation = Observation(detailed=enabled)
    token = current.set(observation)
    try:
        yield observation
    finally:
        current.reset(token)


def material():
    return CredentialMaterial(credential_id="fixture", provider="google", model="gemini-3.1-flash-lite",
        fingerprint="fixture", purpose=CredentialPurpose.MESSAGE_LLM, _secret="synthetic-key", thinking_level="high")


def graph_run(monkeypatch, failure, repaired, capture):
    intent, resolved = _resolved()
    if failure == "counterpart":
        resolved = replace(resolved, relationship_to_world_character_id="other-private-identity")
    calls = []
    async def generate(**kwargs):
        calls.append({key: kwargs[key] for key in ("system_prompt", "user_prompt", "response_schema", "max_output_tokens", "thinking_level") if key in kwargs})
        kwargs["tracker"].next_call_order()
        kwargs["tracker"].next_provider_call_order()
        payload = _plan_payload(resolved)
        if failure == "direction" and (len(calls) == 1 or not repaired):
            payload["steps"][0]["parameters"]["direction"] = "incoming"
        return direct_llm.DirectLlmResponse(text=json.dumps(payload), parsed=None, usage={}, finish_reason="STOP")
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    recall = _FakeRecall()
    service = GraphRetrievalPlanningService(planner=DirectLlmGraphRetrievalPlannerProvider(material()), executor=GraphRetrievalPlanExecutor(recall))
    command = GraphRetrievalCommand(user_message="private-question", intent=intent, resolved=resolved, call_tracker=_router_tracker())
    with recording(capture) as observation:
        try:
            result = asyncio.run(service.plan_and_execute(command, now=NOW, deadline_at=DEADLINE))
            outcome = ("success", result.call_tracker)
        except RetrievalContractError as error:
            outcome = (str(error), error.call_tracker)
    return observation, calls, recall.queries, outcome


@pytest.mark.parametrize("failure,repaired", [("direction", False), ("direction", True), ("counterpart", False), (None, False)])
def test_graph_capture_preserves_calls_queries_and_outcome(monkeypatch, failure, repaired):
    off, calls_off, queries_off, outcome_off = graph_run(monkeypatch, failure, repaired, False)
    on, calls_on, queries_on, outcome_on = graph_run(monkeypatch, failure, repaired, True)
    assert calls_off == calls_on
    assert queries_off == queries_on
    assert outcome_off == outcome_on
    assert off.details == []
    rows = [row for row in on.details if row.get("event") == "graph_step"]
    assert rows and on.detail_omitted == 0
    if failure:
        assert {row["phase"] for row in rows} >= {"first", "repair"}
        first = rows[0]
        if failure == "direction":
            assert first["expected_direction"] == "outgoing"
            assert first["returned_direction"] == "incoming"
            assert first["counterpart_check"] == "matched"
        else:
            assert first["counterpart_check"] == "mismatch"
            assert first["expected_identity"] != first["returned_identity"]
            assert first["direction_check"] == "not_evaluated"
        repair = next(row for row in on.details if row.get("event") == "graph_provider" and row["phase"] == "repair")
        assert repair["repair_digest"].startswith("sha256-")
        assert repair["expected_values_supplied"] == "no"
    serialized = json.dumps(on.payload()) + json.dumps([row for row in on.details if row.get("trace_version")])
    for private in ("private-question", "actual-cheolsu", "other-private-identity", "synthetic-key", "철수"):
        assert private not in serialized
    if outcome_on[0] != "success":
        assert not queries_on
        assert not any(row.get("execution_state") == "executor_entered" for row in on.details)
    else:
        assert any(row.get("execution_state") == "completed" for row in on.details)


@pytest.mark.parametrize("bad_value,expected_shape", [(None, "null"), ([], "array"), ("private-secret", "string")])
def test_supervisor_exact_error_shape_and_actual_finish(monkeypatch, bad_value, expected_shape):
    from test_supervisor_native_tools import call
    from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
    args = call("GRAPH", route=RetrievalRoute.GRAPH).arguments()
    args["relationship"] = bad_value
    async def generate(**kwargs):
        kwargs["tracker"].next_provider_call_order()
        return SimpleNamespace(text="private-output", finish_reason="MAX_TOKENS", usage={"thoughts_token_count": 0},
            tool_calls=(ProviderToolCall("GRAPH", args, "private-call-id"),))
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    with recording(True) as observation:
        with pytest.raises(ValueError):
            asyncio.run(DirectLlmSupervisorSelectionProvider(material(), native_controls=True).route(RetrievalRouterRequest(user_message="private-question")))
    row = next(row for row in observation.details if row["event"] == "selection_attempt")
    assert row["finish_reason"] == "MAX_TOKENS"
    assert row["thought_tokens"] == 0
    assert "output_tokens" not in row
    assert row["validation_code"] == "retrieval_router_native_output_incomplete"
    assert next(row for row in observation.details if row["event"] == "selection_fields")["relationship_state"] == expected_shape
    assert "private-" not in json.dumps(observation.details)


def test_detail_bound_and_broken_observer_do_not_escape():
    with recording(True) as observation:
        for _ in range(60):
            emit("graph_execution", axis="graph", phase="execution", execution_state="completed")
        assert len(observation.details) == 24
        assert observation.payload()["events"][-1]["trace_complete"] is False
        @safe_observation
        def broken():
            raise RuntimeError("private-error")
        assert broken() is None
        assert len(json.dumps(observation.payload()).encode()) < 16 * 1024
        assert "private-error" not in json.dumps(observation.payload())


def test_request_local_aliases_do_not_cross_requests(monkeypatch):
    first, *_ = graph_run(monkeypatch, None, False, True)
    second, *_ = graph_run(monkeypatch, None, False, True)
    assert first.trace_aliases == second.trace_aliases
    assert first.trace_aliases is not second.trace_aliases


def test_supervisor_first_and_repair_keep_distinct_field_failures(monkeypatch):
    from test_supervisor_native_tools import call
    from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
    arguments = call("GRAPH", route=RetrievalRoute.GRAPH).arguments()
    arguments["relationship"] = {"perspective": "responding_character", "from": "responding_character",
        "to": None, "dimension": None, "requested_polarity": None}
    async def generate(**kwargs):
        return SimpleNamespace(text="", finish_reason="STOP", usage={},
            tool_calls=(ProviderToolCall("GRAPH", arguments.copy(), "fixture"),))
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    provider = DirectLlmSupervisorSelectionProvider(material(), native_controls=True)
    with recording(True) as observation:
        with pytest.raises(ValueError) as first:
            asyncio.run(provider.route(RetrievalRouterRequest(user_message="fixture")))
        arguments["relationship"] = []
        with pytest.raises(ValueError):
            asyncio.run(provider.route(RetrievalRouterRequest(user_message="fixture", repair_diagnostic=first.value.validation_code)))
    rows = [row for row in observation.details if row["event"] == "selection_attempt"]
    assert [row["phase"] for row in rows] == ["first", "repair"]
    assert rows[0]["validation_code"] != rows[1]["validation_code"]
    assert rows[1]["repair_code"] == first.value.validation_code
    assert rows[0]["field_path"] == "relationship.to"
    assert "output_tokens" not in rows[0]


def test_supervisor_transport_failure_is_not_invented_as_finish_reason(monkeypatch):
    async def generate(**kwargs):
        raise TimeoutError("private-provider-response")
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    with recording(True) as observation:
        with pytest.raises(TimeoutError, match="private-provider-response"):
            asyncio.run(DirectLlmSupervisorSelectionProvider(material(), native_controls=True).route(RetrievalRouterRequest(user_message="fixture")))
    row = observation.details[0]
    assert row["response_state"] == "not_received"
    assert row["finish_reason"] == "not_reported"
    assert row["dispatch_complete"] == "unknown"
    assert "private-provider-response" not in json.dumps(observation.details)


def test_graph_duplicate_reference_identity_is_not_a_mismatch():
    from app.contracts.decision_observation import decision_scope
    from app.domains.relationships.policies.graph_plan_schema import parse_graph_retrieval_plan_payload
    from app.domains.relationships.service.graph_planning import GraphRetrievalPlanValidator
    intent, resolved = _resolved()
    command = GraphRetrievalCommand(user_message="fixture", intent=intent, resolved=resolved, call_tracker=_router_tracker())
    context = GraphRetrievalPlanningService._execution_context(command)
    context = replace(context, entity_bindings=(*context.entity_bindings, ("entity-2", context.entity_bindings[0][1])))
    payload = _plan_payload(resolved)
    payload["steps"][0]["parameters"]["counterpart_ref"] = "entity-2"
    with recording(True) as observation, decision_scope("graph", "first"):
        GraphRetrievalPlanValidator().validate(parse_graph_retrieval_plan_payload(payload), context)
    row = next(row for row in observation.details if row["event"] == "graph_step")
    assert row["counterpart_check"] == "matched"
    assert row["expected_ref_count"] == 2
    assert row["expected_identity"] == row["returned_identity"]
