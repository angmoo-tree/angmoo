"""Graph failure tests use synthetic providers only; no model/data access."""
import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.contracts.retrieval_observation import Observation, current
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.service.response_workflow import _classify_failure
from app.domains.relationships.contracts.graph_diagnostics import GraphAttemptObservation
from app.integrations.direct_llm import DirectLlmJsonError
from test_p8_l_m_graph_retrieval_planner import (
    _resolved, _router_tracker, _FakePlanner, _FakeRecall, _plan_payload,
    NOW, DEADLINE, GraphPlannerOutputError, GraphPlanContractError,
    GraphRetrievalPlanningService, GraphRetrievalCommand,
    GraphRetrievalPlanExecutor, parse_graph_retrieval_plan_payload,
)


class _InterruptiblePlanner(_FakePlanner):
    async def plan(self, request):
        if isinstance(self.outcomes[0], asyncio.CancelledError):
            self.requests.append(request)
            raise self.outcomes.pop(0)
        return await super().plan(request)


def run_failure(*errors, router_repaired=True, detailed=False):
    intent, resolved = _resolved()
    planner = _InterruptiblePlanner(*errors)
    recall = _FakeRecall()
    observation = Observation(detailed=detailed)
    token = current.set(observation)
    try:
        with pytest.raises(BaseException) as captured:
            asyncio.run(GraphRetrievalPlanningService(planner=planner,
                executor=GraphRetrievalPlanExecutor(recall)).plan_and_execute(
                GraphRetrievalCommand(user_message="synthetic", intent=intent, resolved=resolved,
                    call_tracker=_router_tracker(repaired=router_repaired)), now=NOW, deadline_at=DEADLINE))
    finally:
        current.reset(token)
    return captured.value, observation, planner, recall


@pytest.mark.parametrize("detailed", [False, True])
def test_graph_root_error_and_failed_calls_survive_exhausted_router_repair(detailed):
    error, obs, planner, recall = run_failure(GraphPlannerOutputError("JSONDecodeError"), detailed=detailed)
    assert str(error) == "graph_planner_request_wide_repair_exhausted"
    assert len(planner.requests) == 1 and not recall.queries
    assert error.call_tracker["logical_total"] == 3
    assert error.call_tracker["physical_counts"]["graph_planner"] == 1
    assert error.call_tracker["repair_node"] == "retrieval_router"
    assert error.graph_failure_diagnostic.rejections[0].validation_code == "JSONDecodeError"
    row = next(e for e in obs.events if e["event"] == "planner_validation")
    assert row["physical_attempts"] == row["logical_calls"] == 1
    assert row["failure_stage"] == "json_decode"


def test_first_and_repair_diagnostics_remain_separate_without_payloads():
    first = GraphPlannerOutputError("GraphPlanContractError")
    direct = DirectLlmJsonError("private body", failure_class="json_parse_failed",
        parse_error_type="GraphPlanContractError", json_error_diagnostics=[{
            "finish_reason": "STOP", "shape_hint": "schema_validation",
            "response_length": 231, "preview_head": "private secret"}])
    direct.__cause__ = GraphPlanContractError("graph_plan_direction_required")
    first.__cause__ = direct
    error, obs, planner, _ = run_failure(first, GraphPlannerOutputError("JSONDecodeError", physical_attempt_count=2), router_repaired=False)
    rows = error.graph_failure_diagnostic.rejections
    assert [r.validation_code for r in rows] == ["graph_plan_direction_required", "JSONDecodeError"]
    assert rows[0].finish_reason == "STOP" and rows[0].response_chars == 231
    assert rows[0].failure_stage == "schema_validation"
    assert error.call_tracker["logical_counts"]["graph_planner"] == 2
    assert error.call_tracker["physical_counts"]["graph_planner"] == 3
    assert len(planner.requests) == 2
    assert "private" not in json.dumps(obs.payload())
    assert "private" not in json.dumps(error.graph_failure_diagnostic.payload())


def test_validator_failure_does_not_count_provider_twice():
    _, resolved = _resolved()
    payload = _plan_payload(resolved)
    payload["envelope_hash"] = "a" * 64
    error, _, _, recall = run_failure(parse_graph_retrieval_plan_payload(payload))
    assert error.call_tracker["physical_counts"]["graph_planner"] == 1
    assert error.graph_failure_diagnostic.rejections[0].validation_code == "graph_plan_binding_mismatch"
    assert not recall.queries


@pytest.mark.parametrize("exception", [TimeoutError, asyncio.CancelledError, RuntimeError])
@pytest.mark.parametrize("known", [False, True])
def test_interrupted_provider_preserves_known_counts_without_inventing_attempts(exception, known):
    failure = exception("private")
    if known:
        failure.graph_attempt = GraphAttemptObservation(2)
    error, obs, _, recall = run_failure(failure)
    assert error.call_tracker["physical_counts"]["graph_planner"] == (2 if known else 0)
    assert error.graph_failure_diagnostic.physical_count_complete is known
    assert not recall.queries
    if exception is asyncio.CancelledError:
        assert isinstance(error, asyncio.CancelledError)
    assert "private" not in json.dumps(obs.payload())


def test_unknown_text_never_becomes_a_graph_code():
    error, obs, _, _ = run_failure(GraphPlannerOutputError("graph_private_secret_not_an_error_code"))
    assert error.graph_failure_diagnostic.rejections[0].validation_code == "unknown"
    assert "private_secret" not in json.dumps(obs.payload())


def test_repair_success_keeps_existing_prompt_and_counts():
    intent, resolved = _resolved()
    plan = parse_graph_retrieval_plan_payload(_plan_payload(resolved))
    planner = _FakePlanner(GraphPlannerOutputError("JSONDecodeError"), plan)
    result = asyncio.run(GraphRetrievalPlanningService(planner=planner,
        executor=GraphRetrievalPlanExecutor(_FakeRecall())).plan_and_execute(
        GraphRetrievalCommand(user_message="synthetic", intent=intent, resolved=resolved,
            call_tracker=_router_tracker()), now=NOW, deadline_at=DEADLINE))
    assert result.metrics.repair_used
    assert result.call_tracker["physical_counts"]["graph_planner"] == 2
    assert planner.requests[1].repair_diagnostic == "JSONDecodeError"


def test_request_rejected_before_planner_has_zero_dispatches():
    intent, resolved = _resolved()
    planner = _FakePlanner()
    with pytest.raises(RetrievalContractError) as captured:
        asyncio.run(GraphRetrievalPlanningService(planner=planner,
            executor=GraphRetrievalPlanExecutor(_FakeRecall())).plan_and_execute(
            GraphRetrievalCommand(user_message="synthetic", intent=intent,
                resolved=replace(resolved, intent_hash="a" * 64), call_tracker=_router_tracker()),
            now=NOW, deadline_at=DEADLINE))
    assert not planner.requests
    assert captured.value.call_tracker["physical_counts"]["graph_planner"] == 0
    assert captured.value.graph_failure_diagnostic.rejections[0].failure_stage == "request"


@pytest.mark.parametrize("dispatches", [0, 2])
@pytest.mark.parametrize("failure_type", [TimeoutError, RuntimeError, asyncio.CancelledError])
def test_real_adapter_reports_dispatches_even_without_completed_response(monkeypatch, dispatches, failure_type):
    from app.integrations.llm.graph_retrieval_planner import DirectLlmGraphRetrievalPlannerProvider
    from app.domains.identity.contracts import CredentialPurpose
    intent, resolved = _resolved()
    async def fail(**kwargs):
        for _ in range(dispatches):
            kwargs["tracker"].next_provider_call_order()
        raise failure_type("private-provider-detail")
    monkeypatch.setattr("app.integrations.llm.graph_retrieval_planner.direct_llm.generate_json", fail)
    material = SimpleNamespace(purpose=CredentialPurpose.MESSAGE_LLM, model="gemini-3.1-flash-lite",
        thinking_level="high", credential_id="synthetic", fingerprint="synthetic", provider="google", reveal=lambda: "synthetic")
    request = GraphRetrievalPlanningService._provider_request(GraphRetrievalCommand(
        user_message="synthetic", intent=intent, resolved=resolved, call_tracker=_router_tracker()))
    with pytest.raises(failure_type) as captured:
        asyncio.run(DirectLlmGraphRetrievalPlannerProvider(material).plan(request))
    assert captured.value.graph_attempt == GraphAttemptObservation(dispatches)


def test_malformed_optional_diagnostics_do_not_mask_original_failure():
    failure = GraphPlannerOutputError("JSONDecodeError")
    failure.json_error_diagnostics = [{"finish_reason": ["secret"], "response_length": "secret"}]
    error, obs, _, _ = run_failure(failure)
    assert str(error) == "graph_planner_request_wide_repair_exhausted"
    assert error.graph_failure_diagnostic.rejections[0].finish_reason is None
    assert len(json.dumps(error.graph_failure_diagnostic.payload()).encode()) < 2048
    assert "secret" not in json.dumps(obs.payload())


def _bind_both_tools(coordinator, intent, resolved):
    from app.runtime.chat.retrieval_tools import (
        RetrievalToolExecution, ToolPlanningService, active_tool_execution, parallel_tools,
    )
    from app.domains.chat.contracts.supervisor_selection import SelectionToolCall, SEMANTIC_FIELDS
    coordinator._canonical = ToolPlanningService("CANONICAL", coordinator._canonical)
    coordinator._graph = ToolPlanningService("GRAPH", coordinator._graph)
    coordinator._parallel_runner = parallel_tools
    args = json.dumps({key: intent.payload()[key] for key in SEMANTIC_FIELDS})
    calls = tuple(SelectionToolCall(f"native-{i}", name, args) for i, name in enumerate(("CANONICAL", "GRAPH")))
    execution = RetrievalToolExecution()
    execution.bind(SimpleNamespace(intent=intent, resolved=resolved, proposed_tool_calls=calls),
        SimpleNamespace(assert_active=lambda _: None), {})
    return active_tool_execution, active_tool_execution.set(execution)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("first", ["graph", "canonical"])
@pytest.mark.parametrize("canonical_fails", [False, True])
def test_both_parallel_final_counts_and_both_errors_survive(native, first, canonical_fails):
    import test_p8_l_n_both_workflow_coordinator as f
    from app.domains.chat.contracts.call_tracker import restore_call_tracker_snapshot, LlmNode
    from app.domains.chat.contracts.graph_failure import graph_failure_diagnostic
    async def run():
        intent, resolved = f._resolved(intent_name="mixed_evidence", hint="INDEPENDENT_PARALLEL")
        ready = asyncio.Event()
        class Delayed:
            def __init__(self, axis, delegate): self.axis, self.delegate = axis, delegate
            async def plan(self, request):
                if self.axis != first: await ready.wait()
                try: return await self.delegate.plan(request)
                finally:
                    if self.axis == first: ready.set()
        canonical = f._CanonicalPlanner(f.CanonicalPlannerOutputError("JSONDecodeError") if canonical_fails else f._canonical_plan(resolved))
        graph = f._GraphPlanner(GraphPlannerOutputError("JSONDecodeError", physical_attempt_count=2))
        coordinator, _, _ = f._coordinator(resolved,
            canonical_planner=Delayed("canonical", canonical), graph_planner=Delayed("graph", graph))
        command = f._command(intent, resolved)
        tracker = restore_call_tracker_snapshot(command.call_tracker, deadline_at=f.DEADLINE)
        tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=f.NOW, repair=True)
        tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=f.NOW)
        context = _bind_both_tools(coordinator, intent, resolved) if native else None
        try:
            with pytest.raises(RetrievalContractError) as captured:
                await coordinator.coordinate(replace(command, call_tracker=tracker.snapshot()), now=f.NOW, deadline_at=f.DEADLINE)
        finally:
            if context: context[0].reset(context[1])
        failure = captured.value
        assert failure.call_tracker["logical_total"] == 4
        assert failure.call_tracker["physical_total"] == 5
        assert failure.call_tracker["physical_counts"]["canonical_planner"] == 1
        assert failure.call_tracker["physical_counts"]["graph_planner"] == 2
        assert graph_failure_diagnostic(failure, include_sibling=True).rejections[0].validation_code == "JSONDecodeError"
        assert str(failure).startswith("canonical_" if canonical_fails else "graph_")
        assert len(canonical.requests) == len(graph.requests) == 1
    asyncio.run(run())


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("recipe,intent_name,canonical_count", [
    ("GRAPH_THEN_CANONICAL", "relationship_cause", 0),
    ("CANONICAL_THEN_GRAPH", "event_aggregation", 1),
])
def test_both_sequential_failure_counts_only_started_axes(native, recipe, intent_name, canonical_count):
    import test_p8_l_n_both_workflow_coordinator as f
    async def run():
        intent, resolved = f._resolved(intent_name=intent_name, hint=recipe)
        graph = f._GraphPlanner(GraphPlannerOutputError("JSONDecodeError"), GraphPlannerOutputError("JSONDecodeError"))
        coordinator, canonical, _ = f._coordinator(resolved, graph_planner=graph)
        context = _bind_both_tools(coordinator, intent, resolved) if native else None
        try:
            with pytest.raises(RetrievalContractError) as captured:
                await coordinator.coordinate(f._command(intent, resolved), now=f.NOW, deadline_at=f.DEADLINE)
        finally:
            if context: context[0].reset(context[1])
        assert len(canonical.requests) == canonical_count
        assert captured.value.call_tracker["physical_counts"]["canonical_planner"] == canonical_count
        assert captured.value.call_tracker["physical_counts"]["graph_planner"] == 2
        assert captured.value.call_tracker["repair_node"] == "graph_planner"
    asyncio.run(run())


@pytest.mark.parametrize("native", [False, True])
def test_both_cancellation_waits_for_graph_dispatch_accounting(native):
    import test_p8_l_n_both_workflow_coordinator as f
    async def run():
        intent, resolved = f._resolved(intent_name="mixed_evidence", hint="INDEPENDENT_PARALLEL")
        started = asyncio.Event()
        settled = asyncio.Event()
        class Blocking:
            async def plan(self, request):
                started.set()
                try: await asyncio.Event().wait()
                except asyncio.CancelledError as exc:
                    exc.graph_attempt = GraphAttemptObservation(1)
                    settled.set()
                    raise
        coordinator, _, _ = f._coordinator(resolved, graph_planner=Blocking())
        context = _bind_both_tools(coordinator, intent, resolved) if native else None
        try:
            task = asyncio.create_task(coordinator.coordinate(f._command(intent, resolved), now=f.NOW, deadline_at=f.DEADLINE))
            await asyncio.wait_for(started.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError) as captured: await task
        finally:
            if context: context[0].reset(context[1])
        assert settled.is_set()
        assert captured.value.call_tracker["physical_counts"]["graph_planner"] == 1
        assert captured.value.call_tracker["physical_counts"]["canonical_planner"] == 1
        assert captured.value.graph_failure_diagnostic.terminal_code == "graph_retrieval_cancelled"
    asyncio.run(run())


@pytest.mark.parametrize("code,stage,expected", [
    ("JSONDecodeError", "json_decode", True),
    ("graph_plan_direction_required", "schema_validation", True),
    ("graph_plan_depth_required", "provider_output", True),
    ("graph_plan_hops_required", "provider_output", True),
    ("graph_plan_ranking_required", "schema_validation", True),
    ("JSONDecodeError", "execution", False),
    ("graph_plan_direction_required", "execution_contract", False),
    ("graph_plan_raw_query_forbidden", "schema_validation", False),
    ("graph_plan_forbidden_field", "schema_validation", False),
    ("graph_plan_payload_keys_invalid", "schema_validation", False),
    ("graph_plan_operation_forbidden", "execution_contract", False),
    ("graph_plan_binding_mismatch", "execution_contract", False),
    ("graph_plan_entity_ref_unresolved", "execution_contract", False),
    ("graph_plan_direction_mismatch", "execution_contract", False),
    ("graph_plan_entity_ref_invalid", "schema_validation", False),
    ("GraphPlanContractError", "provider_output", False),
    ("unknown", "provider_output", False),
])
def test_graph_retry_requires_exact_code_and_trusted_stage(code, stage, expected):
    from app.domains.chat.contracts.graph_failure import GraphFailureDiagnostic
    from app.domains.relationships.contracts.graph_diagnostics import GraphRejection
    failure = RetrievalContractError("graph_planner_request_wide_repair_exhausted")
    failure.graph_failure_diagnostic = GraphFailureDiagnostic(str(failure),
        (GraphRejection("first", code, stage),), "retrieval_router", True)
    assert _classify_failure(failure)[:2] == ("retrieval_rejected", expected)


def test_unknown_or_security_first_rejection_does_not_become_retryable_after_format_repair():
    for code in ("unknown", "graph_plan_raw_query_forbidden", "graph_plan_binding_mismatch"):
        failure, _, _, _ = run_failure(GraphPlannerOutputError(code), GraphPlannerOutputError("JSONDecodeError"), router_repaired=False)
        assert _classify_failure(failure)[1] is False


def test_untyped_diagnostic_and_sibling_graph_do_not_override_failure_owner():
    failure = RetrievalContractError("graph_planner_request_wide_repair_exhausted")
    failure.graph_failure_diagnostic = {"validation_code": "JSONDecodeError", "private": "secret"}
    assert _classify_failure(failure)[1] is False
    graph, _, _, _ = run_failure(GraphPlannerOutputError("JSONDecodeError"))
    canonical = RetrievalContractError("canonical_planner_request_wide_repair_exhausted")
    canonical.sibling_graph_failure_diagnostic = graph.graph_failure_diagnostic
    assert _classify_failure(canonical)[1] is False


def test_graph_safe_diagnostic_survives_observation_cap():
    from app.contracts.retrieval_observation import observe
    observation = Observation()
    token = current.set(observation)
    try:
        for index in range(100):
            observe("search", step=index, reason="x" * 80)
        failure, _, _, _ = run_failure(GraphPlannerOutputError("JSONDecodeError"))
        row = failure.graph_failure_diagnostic.rejections[0]
        observe("graph_failure", axis="graph", terminal_code=str(failure), **row.payload())
    finally: current.reset(token)
    payload = observation.payload()
    assert len(payload["events"]) <= 48
    assert len(json.dumps(payload, ensure_ascii=True).encode()) <= 16384
    assert payload["events"][-1]["event"] == "graph_failure"
    assert _classify_failure(failure)[1] is True
