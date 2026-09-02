from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.chat.public import (
    BothRetrievalCommand,
    BothRetrievalWorkflowCoordinator,
    CanonicalRetrievalCommand,
    CanonicalRetrievalPlanningService,
    GraphRetrievalPlanningService,
    LlmNode,
    ResolvedEntityBinding,
    ResolvedRetrievalEnvelope,
    RetrievalContractError,
    RetrievalHardCaps,
    RetrievalRoute,
    RouteAwareCallTracker,
    WorkflowAxis,
    WorkflowDependencyKind,
    WorkflowRecipe,
    parse_retrieval_intent_payload,
    select_workflow_recipe,
)
from app.domains.memory.public import (
    CANONICAL_PRIMITIVE_REGISTRY,
    CanonicalPlannerOutputError,
    CanonicalPlannerProviderResult,
    CanonicalRecallOperation,
    CanonicalRecallRecord,
    CanonicalRecallResult,
    CanonicalRecallStatus,
    CanonicalRetrievalPlanExecutor,
    RecallDocumentKind,
    parse_canonical_retrieval_plan_payload,
)
from app.domains.relationships.public import (
    GRAPH_RECALL_PRIMITIVE_REGISTRY,
    GraphPlannerOutputError,
    GraphPlannerProviderResult,
    GraphRecallEvidence,
    GraphRecallOperation,
    GraphRecallResult,
    GraphRecallSource,
    GraphRecallStatus,
    GraphRetrievalPlanExecutor,
    parse_graph_retrieval_plan_payload,
)


NOW = datetime(2026, 9, 2, 8, tzinfo=UTC)
DEADLINE = NOW + timedelta(seconds=30)
EVENT_ID = "event-relationship-42"
COUNTERPART_ID = "actual-cheolsu-never-in-prompt"


def _intent_payload(
    *,
    intent: str = "relationship_cause",
    hint: str = "GRAPH_THEN_CANONICAL",
    route: str = "BOTH",
) -> dict:
    return {
        "version": "retrieval-intent.v1",
        "decision": "RETRIEVAL",
        "route": route,
        "intent": intent,
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
        "coordination_hint": hint if route == "BOTH" else None,
        "clarification_slot": None,
    }


def _resolved(
    *,
    intent_name: str = "relationship_cause",
    hint: str = "GRAPH_THEN_CANONICAL",
    memory_enabled: bool = True,
    observable: bool = True,
):
    intent = parse_retrieval_intent_payload(
        _intent_payload(intent=intent_name, hint=hint)
    )
    resolved = ResolvedRetrievalEnvelope.bind_intent(
        intent,
        request_id="request-both-1",
        owner_id="actual-owner-never-in-prompt",
        world_id="actual-world-never-in-prompt",
        requester_world_character_id="actual-requester-never-in-prompt",
        responding_world_character_id="actual-responder-never-in-prompt",
        entity_bindings=(
            ResolvedEntityBinding(
                ref="entity-1",
                world_character_id=COUNTERPART_ID,
            ),
        ),
        relationship_from_world_character_id="actual-responder-never-in-prompt",
        relationship_to_world_character_id=COUNTERPART_ID,
        absolute_time_from=None,
        absolute_time_to=None,
        memory_enabled=memory_enabled,
        canonical_operation_allowlist=tuple(
            sorted(operation.value for operation in CANONICAL_PRIMITIVE_REGISTRY)
        ),
        graph_operation_allowlist=tuple(
            sorted(operation.value for operation in GRAPH_RECALL_PRIMITIVE_REGISTRY)
        ),
        caps=RetrievalHardCaps(row_limit=6, max_hops=2, fanout_limit=4),
        observable=observable,
    )
    return intent, resolved


def _canonical_plan(resolved: ResolvedRetrievalEnvelope):
    return parse_canonical_retrieval_plan_payload(
        {
            "version": "canonical-plan.v1",
            "request_id": resolved.request_id,
            "envelope_version": resolved.version,
            "envelope_hash": resolved.envelope_hash,
            "steps": [
                {
                    "id": "events",
                    "operation": "list_social_events",
                    "input_ref": None,
                    "parameters": {"counterpart_ref": "entity-1", "limit": 6},
                }
            ],
        }
    )


def _graph_plan(resolved: ResolvedRetrievalEnvelope):
    return parse_graph_retrieval_plan_payload(
        {
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
                        "limit": 6,
                    },
                }
            ],
        }
    )


class _ParallelBarrier:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.ready = asyncio.Event()

    async def arrive(self, name: str) -> None:
        self.started.append(name)
        if len(self.started) == 2:
            self.ready.set()
        await asyncio.wait_for(self.ready.wait(), timeout=1)


class _CanonicalPlanner:
    def __init__(self, *outcomes, log=None, barrier=None) -> None:
        self.outcomes = list(outcomes)
        self.requests = []
        self.log = log
        self.barrier = barrier

    async def plan(self, request):
        self.requests.append(request)
        if self.log is not None:
            self.log.append("canonical")
        if self.barrier is not None:
            await self.barrier.arrive("canonical")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return CanonicalPlannerProviderResult(
            plan=outcome,
            provider="fixture",
            model="fixture-canonical",
            physical_attempt_count=1,
        )


class _GraphPlanner:
    def __init__(self, *outcomes, log=None, barrier=None) -> None:
        self.outcomes = list(outcomes)
        self.requests = []
        self.log = log
        self.barrier = barrier

    async def plan(self, request):
        self.requests.append(request)
        if self.log is not None:
            self.log.append("graph")
        if self.barrier is not None:
            await self.barrier.arrive("graph")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return GraphPlannerProviderResult(
            plan=outcome,
            provider="fixture",
            model="fixture-graph",
            physical_attempt_count=1,
        )


class _CanonicalRecall:
    def __init__(self, *, empty: bool = False, duplicate: bool = False) -> None:
        self.empty = empty
        self.duplicate = duplicate
        self.queries = []

    def execute(self, query, *, now=None):
        del now
        self.queries.append(query)
        records = ()
        if not self.empty:
            record = CanonicalRecallRecord(
                reference=f"source:social_event:{EVENT_ID}",
                kind=RecallDocumentKind.SOCIAL_EVENT,
                canonical_source_id=EVENT_ID,
                source_event_id=EVENT_ID,
                text="철수와의 검증된 관계 사건",
                occurred_at=NOW,
                counterpart_world_character_id=COUNTERPART_ID,
            )
            records = (record, record) if self.duplicate else (record,)
        return CanonicalRecallResult(
            operation=CanonicalRecallOperation(query.operation),
            status=CanonicalRecallStatus.READY,
            records=records,
            candidate_count=len(records),
        )


class _GraphRecall:
    def __init__(self, *, empty: bool = False, event_id: str = EVENT_ID) -> None:
        self.empty = empty
        self.event_id = event_id
        self.queries = []

    def execute(self, query, *, graph_projection_enabled=True, now=None):
        del graph_projection_enabled, now
        self.queries.append(query)
        evidence = ()
        characters = ()
        if not self.empty:
            evidence = (
                GraphRecallEvidence(
                    event_id=self.event_id,
                    event_type="relationship_changed",
                    occurred_at=NOW,
                    actor_world_character_id="actual-responder-never-in-prompt",
                    target_world_character_id=COUNTERPART_ID,
                ),
            )
            characters = (COUNTERPART_ID,)
        return GraphRecallResult(
            operation=GraphRecallOperation(query.operation),
            status=GraphRecallStatus.READY,
            source=GraphRecallSource.NONE if self.empty else GraphRecallSource.GRAPH,
            evidence=evidence,
            world_character_ids=characters,
            candidate_count=len(characters),
        )


class _ManyCanonicalRecall:
    def execute(self, query, *, now=None):
        del now
        records = tuple(
            CanonicalRecallRecord(
                reference=f"source:social_event:event-{index}",
                kind=RecallDocumentKind.SOCIAL_EVENT,
                canonical_source_id=f"event-{index}",
                source_event_id=f"event-{index}",
                text=f"검증된 사건 {index}",
                occurred_at=NOW - timedelta(minutes=index),
            )
            for index in range(8)
        )
        return CanonicalRecallResult(
            operation=CanonicalRecallOperation(query.operation),
            status=CanonicalRecallStatus.READY,
            records=records,
            candidate_count=len(records),
        )


def _tracker() -> dict:
    tracker = RouteAwareCallTracker(route=RetrievalRoute.BOTH, deadline_at=DEADLINE)
    tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    return tracker.snapshot()


def _coordinator(
    resolved: ResolvedRetrievalEnvelope,
    *,
    canonical_planner=None,
    graph_planner=None,
    canonical_recall=None,
    graph_recall=None,
):
    canonical_planner = canonical_planner or _CanonicalPlanner(
        _canonical_plan(resolved)
    )
    graph_planner = graph_planner or _GraphPlanner(_graph_plan(resolved))
    canonical_recall = canonical_recall or _CanonicalRecall()
    graph_recall = graph_recall or _GraphRecall()
    return (
        BothRetrievalWorkflowCoordinator(
            canonical=CanonicalRetrievalPlanningService(
                planner=canonical_planner,
                executor=CanonicalRetrievalPlanExecutor(canonical_recall),
            ),
            graph=GraphRetrievalPlanningService(
                planner=graph_planner,
                executor=GraphRetrievalPlanExecutor(graph_recall),
            ),
        ),
        canonical_planner,
        graph_planner,
    )


def _command(intent, resolved):
    return BothRetrievalCommand(
        user_message="철수와 내가 왜 싸웠지?",
        thread_id="actual-thread-never-in-prompt",
        intent=intent,
        resolved=resolved,
        call_tracker=_tracker(),
    )


def test_registry_overrides_an_incompatible_router_hint_by_intent() -> None:
    intent, _resolved_envelope = _resolved(hint="INDEPENDENT_PARALLEL")
    selection = select_workflow_recipe(intent)
    assert selection.requested is WorkflowRecipe.INDEPENDENT_PARALLEL
    assert selection.selected is WorkflowRecipe.GRAPH_THEN_CANONICAL
    assert selection.hint_accepted is False
    assert selection.spec.normal_planner_call_cap == 2


def test_graph_then_canonical_binds_opaque_event_dependency_and_intersects() -> None:
    intent, resolved = _resolved()
    order: list[str] = []
    coordinator, canonical_planner, graph_planner = _coordinator(
        resolved,
        canonical_planner=_CanonicalPlanner(_canonical_plan(resolved), log=order),
        graph_planner=_GraphPlanner(_graph_plan(resolved), log=order),
    )
    result = asyncio.run(
        coordinator.coordinate(
            _command(intent, resolved),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )

    assert order == ["graph", "canonical"]
    assert result.dependency is not None
    assert result.dependency.opaque_reference == "graph-result.event_refs"
    assert result.dependency.kind is WorkflowDependencyKind.EVENT_REFERENCES
    assert result.dependency.actual_values == (EVENT_ID,)
    assert result.workflow is not None
    assert result.workflow.recipe is WorkflowRecipe.GRAPH_THEN_CANONICAL
    assert result.metrics.coordinator_llm_calls == 0
    assert result.metrics.joined_reference_count == 1
    assert result.references[0].axes == (
        WorkflowAxis.CANONICAL,
        WorkflowAxis.GRAPH,
    )
    assert result.references[0].event_references == (EVENT_ID,)
    assert result.call_tracker["logical_total"] == 3
    assert result.call_tracker["normal_full_path_cap"] == 4
    assert result.call_tracker["logical_counts"]["character_response_generator"] == 0
    assert len(canonical_planner.requests) == len(graph_planner.requests) == 1
    assert not hasattr(canonical_planner.requests[0], "actual_values")
    assert not hasattr(graph_planner.requests[0], "actual_values")


def test_graph_dependency_zero_short_circuits_canonical_planner() -> None:
    intent, resolved = _resolved()
    canonical_planner = _CanonicalPlanner(_canonical_plan(resolved))
    coordinator, _canonical, graph_planner = _coordinator(
        resolved,
        canonical_planner=canonical_planner,
        graph_recall=_GraphRecall(empty=True),
    )
    result = asyncio.run(
        coordinator.coordinate(
            _command(intent, resolved),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )

    assert len(graph_planner.requests) == 1
    assert canonical_planner.requests == []
    assert result.canonical is None
    assert result.workflow is None
    assert result.metrics.downstream_short_circuited is True
    assert result.metrics.downstream_short_circuit_reason == "workflow_dependency_empty"
    assert result.call_tracker["logical_counts"]["canonical_planner"] == 0


def test_independent_recipe_starts_both_planners_in_parallel_and_deduplicates() -> None:
    intent, resolved = _resolved(
        intent_name="mixed_evidence",
        hint="INDEPENDENT_PARALLEL",
    )
    barrier = _ParallelBarrier()
    coordinator, _canonical, _graph = _coordinator(
        resolved,
        canonical_planner=_CanonicalPlanner(
            _canonical_plan(resolved),
            barrier=barrier,
        ),
        graph_planner=_GraphPlanner(_graph_plan(resolved), barrier=barrier),
        canonical_recall=_CanonicalRecall(duplicate=True),
    )
    result = asyncio.run(
        coordinator.coordinate(
            _command(intent, resolved),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )

    assert set(barrier.started) == {"canonical", "graph"}
    assert result.metrics.planners_parallel is True
    assert result.metrics.planner_axes_called == (
        WorkflowAxis.CANONICAL,
        WorkflowAxis.GRAPH,
    )
    assert result.metrics.input_candidate_count == 3
    assert result.metrics.output_reference_count == 1
    assert result.references[0].score >= 1_300
    assert result.call_tracker["logical_counts"]["canonical_planner"] == 1
    assert result.call_tracker["logical_counts"]["graph_planner"] == 1


def test_canonical_then_graph_uses_character_dependency_and_intersection() -> None:
    intent, resolved = _resolved(
        intent_name="event_aggregation",
        hint="CANONICAL_THEN_GRAPH",
    )
    order: list[str] = []
    coordinator, _canonical, _graph = _coordinator(
        resolved,
        canonical_planner=_CanonicalPlanner(_canonical_plan(resolved), log=order),
        graph_planner=_GraphPlanner(_graph_plan(resolved), log=order),
    )
    result = asyncio.run(
        coordinator.coordinate(
            _command(intent, resolved),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )

    assert order == ["canonical", "graph"]
    assert result.dependency is not None
    assert result.dependency.opaque_reference == (
        "canonical-result.world_character_refs"
    )
    assert result.dependency.actual_values == (COUNTERPART_ID,)
    assert result.workflow is not None
    assert result.workflow.recipe is WorkflowRecipe.CANONICAL_THEN_GRAPH
    assert len(result.references) == 1


def test_deterministic_ranking_and_resolved_row_cap_are_stable() -> None:
    intent, resolved = _resolved(
        intent_name="mixed_evidence",
        hint="INDEPENDENT_PARALLEL",
    )

    def execute_once():
        coordinator, _canonical, _graph = _coordinator(
            resolved,
            canonical_recall=_ManyCanonicalRecall(),
            graph_recall=_GraphRecall(event_id="event-unmatched"),
        )
        return asyncio.run(
            coordinator.coordinate(
                _command(intent, resolved),
                now=NOW,
                deadline_at=DEADLINE,
            )
        )

    first = execute_once()
    second = execute_once()
    assert len(first.references) == resolved.caps.row_limit == 6
    assert [reference.rank for reference in first.references] == list(range(1, 7))
    assert [reference.opaque_reference for reference in first.references] == [
        reference.opaque_reference for reference in second.references
    ]


def test_sequential_policy_denial_short_circuits_the_downstream_planner() -> None:
    intent, resolved = _resolved(memory_enabled=False)
    canonical_planner = _CanonicalPlanner(_canonical_plan(resolved))
    coordinator, _canonical, graph_planner = _coordinator(
        resolved,
        canonical_planner=canonical_planner,
    )
    result = asyncio.run(
        coordinator.coordinate(
            _command(intent, resolved),
            now=NOW,
            deadline_at=DEADLINE,
        )
    )

    assert len(graph_planner.requests) == 1
    assert canonical_planner.requests == []
    assert result.metrics.downstream_short_circuit_reason == "canonical_memory_opt_out"


def test_shared_request_repair_token_cannot_be_spent_by_both_parallel_planners() -> None:
    intent, resolved = _resolved(
        intent_name="mixed_evidence",
        hint="INDEPENDENT_PARALLEL",
    )
    canonical_planner = _CanonicalPlanner(
        CanonicalPlannerOutputError("malformed_canonical"),
        _canonical_plan(resolved),
    )
    graph_planner = _GraphPlanner(GraphPlannerOutputError("malformed_graph"))
    coordinator, _canonical, _graph = _coordinator(
        resolved,
        canonical_planner=canonical_planner,
        graph_planner=graph_planner,
    )
    with pytest.raises(
        RetrievalContractError,
        match="graph_planner_request_wide_repair_exhausted",
    ):
        asyncio.run(
            coordinator.coordinate(
                _command(intent, resolved),
                now=NOW,
                deadline_at=DEADLINE,
            )
        )
    assert len(canonical_planner.requests) == 2
    assert len(graph_planner.requests) == 1


def test_specialist_both_route_requires_the_code_owned_coordinator() -> None:
    intent, resolved = _resolved()
    service = CanonicalRetrievalPlanningService(
        planner=_CanonicalPlanner(_canonical_plan(resolved)),
        executor=CanonicalRetrievalPlanExecutor(_CanonicalRecall()),
    )
    with pytest.raises(RetrievalContractError, match="canonical_retrieval_route_invalid"):
        asyncio.run(
            service.plan_and_execute(
                CanonicalRetrievalCommand(
                    user_message="철수와 왜 싸웠어?",
                    thread_id="thread-1",
                    intent=intent,
                    resolved=resolved,
                    call_tracker=_tracker(),
                ),
                now=NOW,
                deadline_at=DEADLINE,
            )
        )


def test_intent_hash_and_started_tracker_fail_closed() -> None:
    intent, resolved = _resolved()
    coordinator, _canonical, _graph = _coordinator(resolved)
    mismatched = replace(resolved, intent_hash="f" * 64)
    with pytest.raises(RetrievalContractError, match="intent_hash_mismatch"):
        asyncio.run(
            coordinator.coordinate(
                _command(intent, mismatched),
                now=NOW,
                deadline_at=DEADLINE,
            )
        )

    tracker = RouteAwareCallTracker(route=RetrievalRoute.BOTH, deadline_at=DEADLINE)
    tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    tracker.record_logical_call(LlmNode.GRAPH_PLANNER, now=NOW)
    tracker.record_physical_attempt(LlmNode.GRAPH_PLANNER, now=NOW)
    with pytest.raises(RetrievalContractError, match="tracker_already_started"):
        asyncio.run(
            coordinator.coordinate(
                replace(_command(intent, resolved), call_tracker=tracker.snapshot()),
                now=NOW,
                deadline_at=DEADLINE,
            )
        )
