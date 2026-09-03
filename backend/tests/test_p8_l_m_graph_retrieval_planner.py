from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.domains.chat.public import (
    GraphRetrievalCommand,
    GraphRetrievalPlanningService,
    LlmNode,
    ResolvedEntityBinding,
    ResolvedRetrievalEnvelope,
    RetrievalHardCaps,
    RetrievalRoute,
    RouteAwareCallTracker,
    parse_retrieval_intent_payload,
)
from app.domains.identity.public import CredentialMaterial, CredentialPurpose
from app.domains.relationships.public import (
    GRAPH_RECALL_PRIMITIVE_REGISTRY,
    GraphPlanContractError,
    GraphPlanExecutionContext,
    GraphPlannerEntity,
    GraphPlannerOutputError,
    GraphPlannerProviderResult,
    GraphPlannerRequest,
    GraphRecallDirection,
    GraphRecallOperation,
    GraphRecallResult,
    GraphRecallScope,
    GraphRecallSource,
    GraphRecallStatus,
    GraphRetrievalPlanExecutor,
    GraphRetrievalPlanValidator,
    graph_retrieval_plan_response_schema,
    parse_graph_retrieval_plan_payload,
)
from app.integrations.llm.graph_retrieval_planner import (
    DirectLlmGraphRetrievalPlannerProvider,
)


NOW = datetime(2026, 9, 2, 6, tzinfo=UTC)
DEADLINE = NOW + timedelta(seconds=30)
CORPUS_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/p8_l/graph_planner_v1/held_out_ko.jsonl"
)


def _intent_payload() -> dict:
    return {
        "version": "retrieval-intent.v1",
        "decision": "RETRIEVAL",
        "route": "GRAPH",
        "intent": "relationship_cause",
        "entities": [
            {"ref": "entity-1", "mention": "철수", "role": "counterpart"}
        ],
        "relationship": {
            "perspective": "responding_character",
            "from": "responding_character",
            "to": "entity-1",
            "dimension": "conflict",
            "requested_polarity": "conflict",
        },
        "time_scope": {"kind": "historical_unspecified", "expression": None},
        "aggregation": None,
        "coordination_hint": None,
        "clarification_slot": None,
    }


def _resolved(*, observable: bool = True, memory_enabled: bool = True) -> tuple:
    intent = parse_retrieval_intent_payload(_intent_payload())
    resolved = ResolvedRetrievalEnvelope.bind_intent(
        intent,
        request_id="request-ref-1",
        owner_id="actual-owner-never-in-prompt",
        world_id="actual-world-never-in-prompt",
        requester_world_character_id="actual-requester-never-in-prompt",
        responding_world_character_id="actual-responder-never-in-prompt",
        entity_bindings=(
            ResolvedEntityBinding(
                ref="entity-1",
                world_character_id="actual-cheolsu-never-in-prompt",
            ),
        ),
        relationship_from_world_character_id="actual-responder-never-in-prompt",
        relationship_to_world_character_id="actual-cheolsu-never-in-prompt",
        absolute_time_from=None,
        absolute_time_to=None,
        memory_enabled=memory_enabled,
        canonical_operation_allowlist=(),
        graph_operation_allowlist=tuple(
            sorted(operation.value for operation in GRAPH_RECALL_PRIMITIVE_REGISTRY)
        ),
        caps=RetrievalHardCaps(row_limit=6, max_hops=2, fanout_limit=4),
        observable=observable,
    )
    return intent, resolved


def _plan_payload(resolved: ResolvedRetrievalEnvelope) -> dict:
    return {
        "version": "graph-plan.v1",
        "request_id": resolved.request_id,
        "envelope_version": resolved.version,
        "envelope_hash": resolved.envelope_hash,
        "steps": [
            {
                "id": "relationship",
                "operation": "direct_relationship",
                "input_ref": None,
                "parameters": {
                    "counterpart_ref": "entity-1",
                    "direction": "outgoing",
                    "limit": 50,
                },
            },
            {
                "id": "evidence",
                "operation": "relationship_evidence",
                "input_ref": "relationship.world_character_refs",
                "parameters": {"direction": "outgoing", "limit": 5},
            },
        ],
    }


class _FakeRecall:
    def __init__(self, *, empty: bool = False) -> None:
        self.queries = []
        self.empty = empty
        self.graph_projection_flags = []

    def execute(self, query, *, graph_projection_enabled=True, now=None):
        del now
        self.queries.append(query)
        self.graph_projection_flags.append(graph_projection_enabled)
        world_character_ids = ()
        if not self.empty and query.counterpart_world_character_id is not None:
            world_character_ids = (query.counterpart_world_character_id,)
        return GraphRecallResult(
            operation=query.operation,
            status=GraphRecallStatus.READY,
            source=(GraphRecallSource.NONE if self.empty else GraphRecallSource.GRAPH),
            world_character_ids=world_character_ids,
            candidate_count=len(world_character_ids),
        )


class _FakePlanner:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.requests = []

    async def plan(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return GraphPlannerProviderResult(
            plan=outcome,
            provider="fixture",
            model="fixture-graph-planner",
            physical_attempt_count=1,
        )


def _router_tracker(*, repaired: bool = False) -> dict:
    tracker = RouteAwareCallTracker(route=RetrievalRoute.GRAPH, deadline_at=DEADLINE)
    tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    if repaired:
        tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=NOW, repair=True)
        tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    return tracker.snapshot()


def _execution_context(
    resolved: ResolvedRetrievalEnvelope,
    *,
    bind_direction: bool = True,
) -> GraphPlanExecutionContext:
    return GraphPlanExecutionContext(
        request_id=resolved.request_id,
        envelope_version=resolved.version,
        envelope_hash=resolved.envelope_hash,
        scope=GraphRecallScope(
            resolved.owner_id,
            resolved.world_id,
            resolved.responding_world_character_id,
        ),
        entity_bindings=tuple(
            (binding.ref, binding.world_character_id)
            for binding in resolved.entity_bindings
        ),
        operation_allowlist=resolved.graph_operation_allowlist,
        row_limit=resolved.caps.row_limit,
        max_hops=resolved.caps.max_hops,
        fanout_limit=resolved.caps.fanout_limit,
        relationship_from_world_character_id=(
            resolved.relationship_from_world_character_id if bind_direction else None
        ),
        relationship_to_world_character_id=(
            resolved.relationship_to_world_character_id if bind_direction else None
        ),
    )


def test_provider_schema_is_graph_only_and_strict_parser_normalizes() -> None:
    _intent, resolved = _resolved()
    schema = graph_retrieval_plan_response_schema()
    schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    assert set(
        schema["properties"]["steps"]["items"]["properties"]["operation"][
            "enum"
        ]
    ) == {operation.value for operation in GraphRecallOperation}
    assert "search_thread_messages" not in schema_text
    assert "canonical_event_details" not in schema_text
    assert "cypher" not in schema_text.casefold()

    plan = parse_graph_retrieval_plan_payload(_plan_payload(resolved))
    assert plan.request_id == resolved.request_id
    assert plan.steps[0].parameters == (
        ("counterpart_ref", "entity-1"),
        ("direction", "outgoing"),
        ("limit", 50),
    )


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda payload: payload["steps"][0].update(
                {"operation": "search_thread_messages"}
            ),
            "operation_unknown",
        ),
        (
            lambda payload: payload["steps"][0]["parameters"].update(
                {"world_character_id": "fabricated"}
            ),
            "forbidden_field",
        ),
        (
            lambda payload: payload["steps"][0]["parameters"].update(
                {"query": "MATCH (n) RETURN n"}
            ),
            "forbidden_field",
        ),
        (
            lambda payload: payload["steps"][1].update(
                {"input_ref": "canonical.source_refs"}
            ),
            "cross_axis_ref_forbidden",
        ),
        (
            lambda payload: payload["steps"][0]["parameters"].pop("direction"),
            "direction_required",
        ),
        (
            lambda payload: payload["steps"][1].update(
                {"input_ref": "evidence.world_character_refs"}
            ),
            "reference_invalid",
        ),
    ],
)
def test_parser_rejects_cross_catalog_ids_queries_and_bad_dependencies(
    mutate,
    error: str,
) -> None:
    _intent, resolved = _resolved()
    payload = _plan_payload(resolved)
    mutate(payload)
    with pytest.raises(GraphPlanContractError, match=error):
        parse_graph_retrieval_plan_payload(payload)


def test_validator_clamps_code_caps_and_executor_injects_actual_scope() -> None:
    _intent, resolved = _resolved()
    payload = _plan_payload(resolved)
    payload["steps"] = [
        {
            "id": "path",
            "operation": "shortest_path",
            "input_ref": None,
            "parameters": {
                "counterpart_ref": "entity-1",
                "direction": "outgoing",
                "max_hops": 3,
                "limit": 50,
            },
        }
    ]
    plan = parse_graph_retrieval_plan_payload(payload)
    recall = _FakeRecall()
    context = _execution_context(resolved)
    result = GraphRetrievalPlanExecutor(recall).execute(plan, context, now=NOW)

    assert result.limit_clamped_steps == ("path",)
    assert result.hop_clamped_steps == ("path",)
    query = recall.queries[0]
    assert query.scope == context.scope
    assert query.counterpart_world_character_id == (
        "actual-cheolsu-never-in-prompt"
    )
    assert query.direction is GraphRecallDirection.OUTGOING
    assert query.max_hops == 2
    assert query.limit == 6


def test_empty_dependency_short_circuits_without_invalid_graph_query() -> None:
    _intent, resolved = _resolved()
    plan = parse_graph_retrieval_plan_payload(_plan_payload(resolved))
    recall = _FakeRecall(empty=True)
    result = GraphRetrievalPlanExecutor(recall).execute(
        plan,
        _execution_context(resolved),
        now=NOW,
    )
    assert len(recall.queries) == 1
    assert result.steps[1].dependency_short_circuited is True
    assert result.steps[1].results[0].reason_code == "graph_dependency_empty"


def test_graph_route_calls_one_specialist_and_preserves_three_call_cap() -> None:
    intent, resolved = _resolved()
    plan = parse_graph_retrieval_plan_payload(_plan_payload(resolved))
    planner = _FakePlanner(plan)
    recall = _FakeRecall()
    result = asyncio.run(
        GraphRetrievalPlanningService(
            planner=planner,
            executor=GraphRetrievalPlanExecutor(recall),
        ).plan_and_execute(
            GraphRetrievalCommand(
                user_message="철수랑 내가 왜 싸웠지?",
                intent=intent,
                resolved=resolved,
                call_tracker=_router_tracker(),
                graph_projection_enabled=False,
            ),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )

    assert len(planner.requests) == 1
    request = planner.requests[0]
    assert request.entities[0].ref == "entity-1"
    assert request.max_hops_hint == 2
    assert not hasattr(request, "owner_id")
    assert not hasattr(request, "world_id")
    assert result.metrics.first_pass_valid is True
    assert result.metrics.planner_logical_calls == 1
    assert result.call_tracker["logical_total"] == 2
    assert result.call_tracker["normal_full_path_cap"] == 3
    assert result.execution is not None
    assert recall.graph_projection_flags == [False, False]


def test_graph_planner_uses_only_remaining_request_wide_repair() -> None:
    intent, resolved = _resolved()
    plan = parse_graph_retrieval_plan_payload(_plan_payload(resolved))
    planner = _FakePlanner(GraphPlannerOutputError("malformed_json"), plan)
    result = asyncio.run(
        GraphRetrievalPlanningService(
            planner=planner,
            executor=GraphRetrievalPlanExecutor(_FakeRecall()),
        ).plan_and_execute(
            GraphRetrievalCommand(
                user_message="철수와 왜 싸웠어?",
                intent=intent,
                resolved=resolved,
                call_tracker=_router_tracker(),
            ),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )
    assert len(planner.requests) == 2
    assert planner.requests[1].repair_diagnostic == "malformed_json"
    assert result.metrics.repair_used is True
    assert result.call_tracker["repair_node"] == "graph_planner"
    assert result.call_tracker["logical_counts"]["graph_planner"] == 2


def test_router_repair_prevents_second_request_wide_graph_repair() -> None:
    intent, resolved = _resolved()
    planner = _FakePlanner(GraphPlannerOutputError("malformed_json"))
    with pytest.raises(
        Exception,
        match="graph_planner_request_wide_repair_exhausted",
    ):
        asyncio.run(
            GraphRetrievalPlanningService(
                planner=planner,
                executor=GraphRetrievalPlanExecutor(_FakeRecall()),
            ).plan_and_execute(
                GraphRetrievalCommand(
                    user_message="철수와 왜 싸웠어?",
                    intent=intent,
                    resolved=resolved,
                    call_tracker=_router_tracker(repaired=True),
                ),
                now=NOW,
                deadline_at=DEADLINE,
            )
        )
    assert len(planner.requests) == 1


def test_unobservable_graph_scope_short_circuits_but_memory_off_does_not() -> None:
    intent, resolved = _resolved(observable=False)
    planner = _FakePlanner()
    recall = _FakeRecall()
    result = asyncio.run(
        GraphRetrievalPlanningService(
            planner=planner,
            executor=GraphRetrievalPlanExecutor(recall),
        ).plan_and_execute(
            GraphRetrievalCommand(
                user_message="관계를 알려줘",
                intent=intent,
                resolved=resolved,
                call_tracker=_router_tracker(),
            ),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )
    assert result.metrics.short_circuit_reason == "graph_scope_unobservable"
    assert planner.requests == []
    assert recall.queries == []

    intent, resolved = _resolved(memory_enabled=False)
    plan = parse_graph_retrieval_plan_payload(_plan_payload(resolved))
    planner = _FakePlanner(plan)
    result = asyncio.run(
        GraphRetrievalPlanningService(
            planner=planner,
            executor=GraphRetrievalPlanExecutor(_FakeRecall()),
        ).plan_and_execute(
            GraphRetrievalCommand(
                user_message="현재 관계를 알려줘",
                intent=intent,
                resolved=resolved,
                call_tracker=_router_tracker(),
            ),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )
    assert result.metrics.short_circuited is False
    assert len(planner.requests) == 1


def test_binding_direction_and_unresolved_reference_fail_closed() -> None:
    _intent, resolved = _resolved()
    payload = _plan_payload(resolved)
    payload["steps"][0]["parameters"]["counterpart_ref"] = "entity-9"
    plan = parse_graph_retrieval_plan_payload(payload)
    context = _execution_context(resolved)
    with pytest.raises(GraphPlanContractError, match="entity_ref_unresolved"):
        GraphRetrievalPlanValidator().validate(plan, context)
    with pytest.raises(GraphPlanContractError, match="binding_mismatch"):
        GraphRetrievalPlanValidator().validate(
            replace(plan, envelope_hash="f" * 64),
            context,
        )

    payload = _plan_payload(resolved)
    payload["steps"][0]["parameters"]["direction"] = "incoming"
    payload["steps"][1]["parameters"]["direction"] = "incoming"
    with pytest.raises(GraphPlanContractError, match="direction_mismatch"):
        GraphRetrievalPlanValidator().validate(
            parse_graph_retrieval_plan_payload(payload),
            context,
        )


@pytest.mark.parametrize(
    "model",
    ("gemini-3.1-flash-lite", "gemini-3.5-flash-lite"),
)
def test_direct_adapter_has_no_hidden_retry_cypher_or_actual_ids(
    monkeypatch,
    model: str,
) -> None:
    captured = {}
    _intent, resolved = _resolved()

    async def fake_generate_json(**kwargs):
        captured.update(kwargs)
        kwargs["tracker"].next_call_order()
        return kwargs["validator"](_plan_payload(resolved))

    monkeypatch.setattr(
        "app.integrations.llm.graph_retrieval_planner.direct_llm.generate_json",
        fake_generate_json,
    )
    material = CredentialMaterial(
        credential_id="credential-1",
        provider="google",
        model=model,
        fingerprint="fingerprint",
        purpose=CredentialPurpose.MESSAGE_LLM,
        _secret="not-a-real-key",
    )
    result = asyncio.run(
        DirectLlmGraphRetrievalPlannerProvider(material).plan(
            GraphPlannerRequest(
                request_id=resolved.request_id,
                envelope_version=resolved.version,
                envelope_hash=resolved.envelope_hash,
                user_message="철수와 왜 싸웠어?",
                intent="relationship_cause",
                entities=(
                    GraphPlannerEntity(
                        ref="entity-1",
                        mention="철수",
                        role="counterpart",
                    ),
                ),
            )
        )
    )
    assert result.physical_attempt_count == 1
    assert captured["thinking_level"] == "high"
    assert captured["max_output_tokens"] == 3_072
    assert result.thinking_level == "high"
    assert result.max_output_tokens == 3_072
    assert captured["should_retry_json_error"](None, None, {}, 1) is False
    assert "actual-owner-never-in-prompt" not in captured["user_prompt"]
    assert "actual-world-never-in-prompt" not in captured["user_prompt"]
    assert "actual-cheolsu-never-in-prompt" not in captured["user_prompt"]
    assert "not-a-real-key" not in captured["user_prompt"]
    schema_text = json.dumps(captured["response_schema"], sort_keys=True)
    assert "search_thread_messages" not in schema_text
    assert "owner_id" not in schema_text
    assert "cypher" not in schema_text.casefold()


def test_held_out_korean_corpus_covers_all_six_operations_and_executes() -> None:
    rows = [
        json.loads(line)
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 36
    assert len({row["case_id"] for row in rows}) == 36
    operation_counts = Counter(row["expected"]["operation"] for row in rows)
    assert set(operation_counts) == {
        operation.value for operation in GraphRecallOperation
    }
    assert set(operation_counts.values()) == {6}

    _intent, resolved = _resolved()
    context = _execution_context(resolved, bind_direction=False)
    for row in rows:
        expected = row["expected"]
        plan = parse_graph_retrieval_plan_payload(
            _corpus_plan_payload(resolved, expected)
        )
        recall = _FakeRecall()
        execution = GraphRetrievalPlanExecutor(recall).execute(plan, context, now=NOW)
        assert execution.steps[-1].results[-1].status is GraphRecallStatus.READY
        assert execution.steps[-1].results[-1].operation.value == (
            expected["operation"]
        )


def _corpus_plan_payload(
    resolved: ResolvedRetrievalEnvelope,
    expected: dict,
) -> dict:
    operation = expected["operation"]
    parameters: dict[str, str | int | bool] = {
        "direction": expected["direction"],
        "limit": expected["limit"],
    }
    counterpart_ref = expected.get("counterpart_ref")
    if counterpart_ref is not None:
        parameters["counterpart_ref"] = counterpart_ref
    if "ranking" in expected:
        parameters["ranking"] = expected["ranking"]
    if "max_hops" in expected:
        parameters["max_hops"] = expected["max_hops"]
    if "depth" in expected:
        parameters["depth"] = expected["depth"]
    return {
        "version": "graph-plan.v1",
        "request_id": resolved.request_id,
        "envelope_version": resolved.version,
        "envelope_hash": resolved.envelope_hash,
        "steps": [
            {
                "id": "result",
                "operation": operation,
                "input_ref": None,
                "parameters": parameters,
            }
        ],
    }
