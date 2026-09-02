from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.domains.chat.public import (
    CanonicalRetrievalCommand,
    CanonicalRetrievalPlanningService,
    LlmNode,
    ResolvedEntityBinding,
    ResolvedRetrievalEnvelope,
    RetrievalHardCaps,
    RetrievalRoute,
    RouteAwareCallTracker,
    parse_retrieval_intent_payload,
)
from app.domains.identity.public import CredentialMaterial, CredentialPurpose
from app.domains.memory.public import (
    CANONICAL_PRIMITIVE_REGISTRY,
    CanonicalPlanContractError,
    CanonicalPlanExecutionContext,
    CanonicalPlannerEntity,
    CanonicalPlannerOutputError,
    CanonicalPlannerProviderResult,
    CanonicalPlannerRequest,
    CanonicalRecallOperation,
    CanonicalRecallRecord,
    CanonicalRecallResult,
    CanonicalRecallStatus,
    CanonicalRetrievalPlanExecutor,
    CanonicalRetrievalPlanValidator,
    MemoryScope,
    RecallDocumentKind,
    canonical_retrieval_plan_response_schema,
    parse_canonical_retrieval_plan_payload,
)
from app.integrations.llm.canonical_retrieval_planner import (
    DirectLlmCanonicalRetrievalPlannerProvider,
)

NOW = datetime(2026, 9, 2, 3, tzinfo=UTC)
DEADLINE = NOW + timedelta(seconds=30)
CORPUS_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/p8_l/canonical_planner_v1/held_out_ko.jsonl"
)


def _intent_payload() -> dict:
    return {
        "version": "retrieval-intent.v1",
        "decision": "RETRIEVAL",
        "route": "CANONICAL",
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
        "time_scope": {
            "kind": "relative",
            "expression": "어제",
        },
        "aggregation": None,
        "coordination_hint": None,
        "clarification_slot": None,
    }


def _resolved(*, memory_enabled: bool = True) -> tuple:
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
        absolute_time_from="2026-09-01T00:00:00Z",
        absolute_time_to="2026-09-02T00:00:00Z",
        memory_enabled=memory_enabled,
        canonical_operation_allowlist=tuple(
            sorted(operation.value for operation in CANONICAL_PRIMITIVE_REGISTRY)
        ),
        graph_operation_allowlist=(),
        caps=RetrievalHardCaps(row_limit=6),
    )
    return intent, resolved


def _plan_payload(resolved: ResolvedRetrievalEnvelope) -> dict:
    return {
        "version": "canonical-plan.v1",
        "request_id": resolved.request_id,
        "envelope_version": resolved.version,
        "envelope_hash": resolved.envelope_hash,
        "steps": [
            {
                "id": "events",
                "operation": "search_thread_messages",
                "input_ref": None,
                "parameters": {
                    "search_text": "철수 갈등 이유",
                    "counterpart_ref": "entity-1",
                    "current_thread": True,
                    "limit": 50,
                },
            },
            {
                "id": "details",
                "operation": "canonical_event_details",
                "input_ref": "events.source_refs",
                "parameters": {"limit": 4},
            },
        ],
    }


class _FakeRecall:
    def __init__(self) -> None:
        self.queries = []

    def execute(self, query, *, now=None):
        del now
        self.queries.append(query)
        text = "철수와의 갈등 원문"
        if query.operation is CanonicalRecallOperation.CANONICAL_EVENT_DETAILS:
            text = "검증된 갈등 사건 상세"
        return CanonicalRecallResult(
            operation=query.operation,
            status=CanonicalRecallStatus.READY,
            records=(
                CanonicalRecallRecord(
                    reference="source:chat_message:42",
                    kind=RecallDocumentKind.THREAD_MESSAGE,
                    canonical_source_id="42",
                    text=text,
                    occurred_at=NOW,
                    counterpart_world_character_id=(
                        query.counterpart_world_character_id
                    ),
                    thread_id=query.thread_id,
                ),
            ),
            candidate_count=1,
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
        return CanonicalPlannerProviderResult(
            plan=outcome,
            provider="fixture",
            model="fixture-canonical-planner",
            physical_attempt_count=1,
        )


def _router_tracker(*, repaired: bool = False) -> dict:
    tracker = RouteAwareCallTracker(
        route=RetrievalRoute.CANONICAL,
        deadline_at=DEADLINE,
    )
    tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    if repaired:
        tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=NOW, repair=True)
        tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    return tracker.snapshot()


def test_provider_schema_is_canonical_only_and_strict_parser_normalizes() -> None:
    _intent, resolved = _resolved()
    schema_text = json.dumps(
        canonical_retrieval_plan_response_schema(),
        ensure_ascii=False,
        sort_keys=True,
    )
    assert set(
        canonical_retrieval_plan_response_schema()["properties"]["steps"]["items"][
            "properties"
        ]["operation"]["enum"]
    ) == {operation.value for operation in CanonicalRecallOperation}
    assert "direct_relationship" not in schema_text
    assert "shortest_path" not in schema_text
    assert "sql" not in schema_text.casefold()

    plan = parse_canonical_retrieval_plan_payload(_plan_payload(resolved))
    assert plan.request_id == resolved.request_id
    assert plan.envelope_hash == resolved.envelope_hash
    assert plan.steps[0].parameters == (
        ("counterpart_ref", "entity-1"),
        ("current_thread", True),
        ("limit", 50),
        ("search_text", "철수 갈등 이유"),
    )


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda payload: payload["steps"][0].update(
                {"operation": "direct_relationship"}
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
                {"search_text": "SELECT * FROM message_messages"}
            ),
            "raw_query_forbidden",
        ),
        (
            lambda payload: payload["steps"][1].update(
                {"input_ref": "graph.evidence_refs"}
            ),
            "cross_axis_ref_forbidden",
        ),
        (
            lambda payload: payload["steps"][0]["parameters"].pop("search_text"),
            "search_text_required",
        ),
        (
            lambda payload: payload["steps"][1].update(
                {"input_ref": "details.source_refs"}
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
    with pytest.raises(CanonicalPlanContractError, match=error):
        parse_canonical_retrieval_plan_payload(payload)


def test_validator_clamps_code_cap_and_executor_injects_actual_scope() -> None:
    _intent, resolved = _resolved()
    plan = parse_canonical_retrieval_plan_payload(_plan_payload(resolved))
    recall = _FakeRecall()
    context = CanonicalPlanExecutionContext(
        request_id=resolved.request_id,
        envelope_version=resolved.version,
        envelope_hash=resolved.envelope_hash,
        scope=MemoryScope(
            owner_id=resolved.owner_id,
            world_id=resolved.world_id,
            subject_world_character_id=resolved.responding_world_character_id,
        ),
        thread_id="actual-thread-never-in-prompt",
        entity_bindings=tuple(
            (item.ref, item.world_character_id) for item in resolved.entity_bindings
        ),
        operation_allowlist=resolved.canonical_operation_allowlist,
        row_limit=resolved.caps.row_limit,
        occurred_from=datetime(2026, 9, 1, tzinfo=UTC),
        occurred_to=datetime(2026, 9, 2, tzinfo=UTC),
    )
    result = CanonicalRetrievalPlanExecutor(recall).execute(plan, context, now=NOW)

    assert result.limit_clamped_steps == ("events",)
    assert len(result.steps) == 2
    first, second = recall.queries
    assert first.scope == context.scope
    assert first.counterpart_world_character_id == "actual-cheolsu-never-in-prompt"
    assert first.thread_id == "actual-thread-never-in-prompt"
    assert first.occurred_from == datetime(2026, 9, 1, tzinfo=UTC)
    assert first.limit == 6
    assert second.source_references == ("source:chat_message:42",)
    assert second.limit == 4


def test_empty_dependency_short_circuits_without_invalid_direct_query() -> None:
    _intent, resolved = _resolved()
    plan = parse_canonical_retrieval_plan_payload(_plan_payload(resolved))

    class _EmptyRecall(_FakeRecall):
        def execute(self, query, *, now=None):
            del now
            self.queries.append(query)
            return CanonicalRecallResult(
                operation=query.operation,
                status=CanonicalRecallStatus.READY,
                records=(),
            )

    recall = _EmptyRecall()
    context = CanonicalPlanExecutionContext(
        request_id=resolved.request_id,
        envelope_version=resolved.version,
        envelope_hash=resolved.envelope_hash,
        scope=MemoryScope(resolved.owner_id, resolved.world_id, resolved.responding_world_character_id),
        thread_id="thread-1",
        entity_bindings=tuple(
            (item.ref, item.world_character_id) for item in resolved.entity_bindings
        ),
        operation_allowlist=resolved.canonical_operation_allowlist,
        row_limit=6,
    )
    result = CanonicalRetrievalPlanExecutor(recall).execute(plan, context, now=NOW)
    assert len(recall.queries) == 1
    assert result.steps[1].dependency_short_circuited is True
    assert result.steps[1].result.reason_code == "canonical_dependency_empty"


def test_canonical_route_calls_one_specialist_and_preserves_three_call_cap() -> None:
    intent, resolved = _resolved()
    plan = parse_canonical_retrieval_plan_payload(_plan_payload(resolved))
    planner = _FakePlanner(plan)
    recall = _FakeRecall()
    service = CanonicalRetrievalPlanningService(
        planner=planner,
        executor=CanonicalRetrievalPlanExecutor(recall),
    )
    result = asyncio.run(
        service.plan_and_execute(
            CanonicalRetrievalCommand(
                user_message="철수랑 내가 어제 왜 싸웠지?",
                thread_id="actual-thread-never-in-prompt",
                intent=intent,
                resolved=resolved,
                call_tracker=_router_tracker(),
            ),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )

    assert len(planner.requests) == 1
    request = planner.requests[0]
    assert request.entities[0].ref == "entity-1"
    assert request.resolved_time_available is True
    assert not hasattr(request, "owner_id")
    assert not hasattr(request, "world_id")
    assert result.metrics.first_pass_valid is True
    assert result.metrics.planner_logical_calls == 1
    assert result.call_tracker["logical_total"] == 2
    assert result.call_tracker["normal_full_path_cap"] == 3
    assert result.execution is not None


def test_canonical_planner_uses_only_remaining_request_wide_repair() -> None:
    intent, resolved = _resolved()
    plan = parse_canonical_retrieval_plan_payload(_plan_payload(resolved))
    planner = _FakePlanner(
        CanonicalPlannerOutputError("malformed_json"),
        plan,
    )
    service = CanonicalRetrievalPlanningService(
        planner=planner,
        executor=CanonicalRetrievalPlanExecutor(_FakeRecall()),
    )
    result = asyncio.run(
        service.plan_and_execute(
            CanonicalRetrievalCommand(
                user_message="철수와 왜 싸웠어?",
                thread_id="thread-1",
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
    assert result.call_tracker["repair_node"] == "canonical_planner"
    assert result.call_tracker["logical_counts"]["canonical_planner"] == 2


def test_router_repair_prevents_a_second_request_wide_planner_repair() -> None:
    intent, resolved = _resolved()
    planner = _FakePlanner(CanonicalPlannerOutputError("malformed_json"))
    service = CanonicalRetrievalPlanningService(
        planner=planner,
        executor=CanonicalRetrievalPlanExecutor(_FakeRecall()),
    )
    with pytest.raises(
        Exception,
        match="canonical_planner_request_wide_repair_exhausted",
    ):
        asyncio.run(
            service.plan_and_execute(
                CanonicalRetrievalCommand(
                    user_message="철수와 왜 싸웠어?",
                    thread_id="thread-1",
                    intent=intent,
                    resolved=resolved,
                    call_tracker=_router_tracker(repaired=True),
                ),
                now=NOW,
                deadline_at=DEADLINE,
            )
        )
    assert len(planner.requests) == 1


def test_memory_off_short_circuits_before_planner_or_recall() -> None:
    intent, resolved = _resolved(memory_enabled=False)
    planner = _FakePlanner()
    recall = _FakeRecall()
    result = asyncio.run(
        CanonicalRetrievalPlanningService(
            planner=planner,
            executor=CanonicalRetrievalPlanExecutor(recall),
        ).plan_and_execute(
            CanonicalRetrievalCommand(
                user_message="과거를 기억해?",
                thread_id="thread-1",
                intent=intent,
                resolved=resolved,
                call_tracker=_router_tracker(),
            ),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )
    assert result.metrics.short_circuited is True
    assert result.metrics.short_circuit_reason == "memory_opt_out"
    assert planner.requests == []
    assert recall.queries == []
    assert result.call_tracker["logical_counts"]["canonical_planner"] == 0


def test_binding_and_unresolved_opaque_reference_fail_closed() -> None:
    _intent, resolved = _resolved()
    payload = _plan_payload(resolved)
    payload["steps"][0]["parameters"]["counterpart_ref"] = "entity-9"
    plan = parse_canonical_retrieval_plan_payload(payload)
    context = CanonicalPlanExecutionContext(
        request_id=resolved.request_id,
        envelope_version=resolved.version,
        envelope_hash=resolved.envelope_hash,
        scope=MemoryScope(resolved.owner_id, resolved.world_id, resolved.responding_world_character_id),
        thread_id="thread-1",
        entity_bindings=(("entity-1", "actual-cheolsu"),),
        operation_allowlist=resolved.canonical_operation_allowlist,
        row_limit=6,
    )
    with pytest.raises(CanonicalPlanContractError, match="entity_ref_unresolved"):
        CanonicalRetrievalPlanValidator().validate(plan, context)
    with pytest.raises(CanonicalPlanContractError, match="binding_mismatch"):
        CanonicalRetrievalPlanValidator().validate(
            replace(plan, envelope_hash="f" * 64),
            context,
        )


def test_direct_adapter_has_no_hidden_retry_or_canonical_ids(monkeypatch) -> None:
    captured = {}
    _intent, resolved = _resolved()

    async def fake_generate_json(**kwargs):
        captured.update(kwargs)
        kwargs["tracker"].next_call_order()
        return kwargs["validator"](_plan_payload(resolved))

    monkeypatch.setattr(
        "app.integrations.llm.canonical_retrieval_planner.direct_llm.generate_json",
        fake_generate_json,
    )
    material = CredentialMaterial(
        credential_id="credential-1",
        provider="google",
        model="fixture-canonical-planner",
        fingerprint="fingerprint",
        purpose=CredentialPurpose.MESSAGE_LLM,
        _secret="not-a-real-key",
    )
    result = asyncio.run(
        DirectLlmCanonicalRetrievalPlannerProvider(material).plan(
            CanonicalPlannerRequest(
                request_id=resolved.request_id,
                envelope_version=resolved.version,
                envelope_hash=resolved.envelope_hash,
                user_message="철수와 왜 싸웠어?",
                intent="relationship_cause",
                entities=(
                    CanonicalPlannerEntity(
                        ref="entity-1",
                        mention="철수",
                        role="counterpart",
                    ),
                ),
                resolved_time_available=True,
            )
        )
    )
    assert result.physical_attempt_count == 1
    assert captured["should_retry_json_error"](None, None, {}, 1) is False
    assert "actual-owner-never-in-prompt" not in captured["user_prompt"]
    assert "actual-world-never-in-prompt" not in captured["user_prompt"]
    assert "not-a-real-key" not in captured["user_prompt"]
    schema_text = json.dumps(captured["response_schema"], sort_keys=True)
    assert "direct_relationship" not in schema_text
    assert "owner_id" not in schema_text


def test_held_out_korean_corpus_covers_all_nine_operations_and_executes() -> None:
    rows = [
        json.loads(line)
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 36
    assert len({row["case_id"] for row in rows}) == 36
    operation_counts = Counter(row["expected"]["operation"] for row in rows)
    assert set(operation_counts) == {
        operation.value for operation in CanonicalRecallOperation
    }
    assert set(operation_counts.values()) == {4}

    _intent, resolved = _resolved()
    context = CanonicalPlanExecutionContext(
        request_id=resolved.request_id,
        envelope_version=resolved.version,
        envelope_hash=resolved.envelope_hash,
        scope=MemoryScope(
            resolved.owner_id,
            resolved.world_id,
            resolved.responding_world_character_id,
        ),
        thread_id="thread-1",
        entity_bindings=tuple(
            (item.ref, item.world_character_id) for item in resolved.entity_bindings
        ),
        operation_allowlist=resolved.canonical_operation_allowlist,
        row_limit=6,
        occurred_from=datetime(2026, 9, 1, tzinfo=UTC),
        occurred_to=datetime(2026, 9, 2, tzinfo=UTC),
    )
    for row in rows:
        expected = row["expected"]
        payload = _corpus_plan_payload(resolved, expected)
        plan = parse_canonical_retrieval_plan_payload(payload)
        recall = _FakeRecall()
        execution = CanonicalRetrievalPlanExecutor(recall).execute(
            plan,
            context,
            now=NOW,
        )
        assert execution.steps[-1].result.status is CanonicalRecallStatus.READY
        assert execution.steps[-1].result.operation.value == expected["operation"]


def _corpus_plan_payload(
    resolved: ResolvedRetrievalEnvelope,
    expected: dict,
) -> dict:
    operation = expected["operation"]
    parameters: dict[str, str | int | bool] = {"limit": 6}
    entity_ref = expected.get("entity_ref")
    if operation == CanonicalRecallOperation.GET_CHARACTER_SUMMARIES.value:
        parameters["entity_ref"] = entity_ref
    elif entity_ref is not None:
        parameters["counterpart_ref"] = entity_ref
    search_text = expected.get("search_text")
    if search_text is not None:
        parameters["search_text"] = search_text
    if operation == CanonicalRecallOperation.SEARCH_THREAD_MESSAGES.value:
        parameters["current_thread"] = bool(expected.get("current_thread"))

    steps = []
    input_ref = None
    if operation == CanonicalRecallOperation.CANONICAL_EVENT_DETAILS.value:
        predecessor_parameters: dict[str, str | int | bool] = {"limit": 6}
        if entity_ref is not None:
            predecessor_parameters["counterpart_ref"] = entity_ref
        steps.append(
            {
                "id": "sources",
                "operation": CanonicalRecallOperation.LIST_SOCIAL_EVENTS.value,
                "input_ref": None,
                "parameters": predecessor_parameters,
            }
        )
        parameters = {"limit": 6}
        input_ref = "sources.source_refs"
    elif operation == CanonicalRecallOperation.GET_POST_THREAD.value:
        predecessor_parameters = {
            "search_text": str(search_text),
            "limit": 6,
        }
        if entity_ref is not None:
            predecessor_parameters["counterpart_ref"] = entity_ref
        steps.append(
            {
                "id": "sources",
                "operation": CanonicalRecallOperation.SEARCH_POSTS.value,
                "input_ref": None,
                "parameters": predecessor_parameters,
            }
        )
        parameters = {"limit": 6}
        input_ref = "sources.source_refs"
    steps.append(
        {
            "id": "result",
            "operation": operation,
            "input_ref": input_ref,
            "parameters": parameters,
        }
    )
    return {
        "version": "canonical-plan.v1",
        "request_id": resolved.request_id,
        "envelope_version": resolved.version,
        "envelope_hash": resolved.envelope_hash,
        "steps": steps,
    }
