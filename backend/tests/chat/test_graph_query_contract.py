"""GC candidate invariants, including executable scope and legacy isolation."""
import json
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.domains.chat.contracts.supervisor_selection import SelectionArgumentOptions, SelectionToolCall, parse_control_selection, effective_calls, model_arguments_schema
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.resolved_envelope import ResolvedRetrievalEnvelope
from app.domains.relationships.contracts.graph_requirements import GraphQueryRequirement as Query
from app.domains.relationships.contracts.graph_plan import GraphPlanContractError
from app.domains.relationships.contracts.graph_planner import GraphPlannerRequest
from app.domains.relationships.policies.graph_query_plan import compile_graph_query_plan
from app.domains.relationships.service.graph_planning import GraphRetrievalPlanValidator, GraphRetrievalPlanExecutor
from chat.test_p8_l_m_graph_retrieval_planner import _resolved, _execution_context, _FakeRecall

OPTIONS = SelectionArgumentOptions(code_coordination=True, graph_query_contract=True)


def arguments(kind="pair", direction="incoming"):
    return {"intent": "relationship_state", "entities": [{"mention": "소라", "role": "counterpart"}],
            "relationship": None, "time_scope": None, "aggregation": None,
            "graph_queries": [{"kind": kind, "direction": direction,
                               "target": None if kind == "collection" else {"kind": "mention", "index": 1},
                               "result_of": None}]}


def select(args, names=("GRAPH",)):
    calls = tuple(SelectionToolCall(f"call-{name}", name, json.dumps(args)) for name in names)
    return parse_control_selection("", calls, options=OPTIONS)


def draft(operation="direct_relationship", requirement=1, **params):
    return {"requirement": requirement, "operation": operation,
            "parameters": {"limit": None, "max_hops": None, "depth": None, "ranking": None, **params}}


def bound(queries):
    _, old = _resolved()
    context = replace(_execution_context(old), envelope_version="resolved-retrieval.v2", graph_queries=tuple(queries))
    request = GraphPlannerRequest(context.request_id, context.envelope_version, context.envelope_hash,
                                  "fixture only", "relationship_state", graph_queries=tuple(queries))
    return request, context


def compile_plan(queries, steps):
    request, context = bound(queries)
    plan = compile_graph_query_plan({"version": "graph-draft.v2", "steps": steps}, request)
    return plan, context


@pytest.mark.parametrize("direction", ["outgoing", "incoming", "bidirectional"])
def test_pair_fixed_direction_and_counterpart_are_executed(direction):
    plan, context = compile_plan([Query("pair", direction, "entity-1")], [draft()])
    recall = _FakeRecall()
    execution = GraphRetrievalPlanExecutor(recall).execute(plan, context)
    expected = ["outgoing", "incoming"] if direction == "bidirectional" else [direction]
    assert [q.direction.value for q in recall.queries] == expected
    assert all(q.counterpart_world_character_id == "actual-cheolsu-never-in-prompt" for q in recall.queries)
    assert all(q.scope == context.scope for q in recall.queries)
    assert len(execution.steps) == len(expected)


def test_missing_half_or_wrong_target_is_rejected_even_after_compilation():
    plan, context = compile_plan([Query("pair", "bidirectional", "entity-1")], [draft()])
    with pytest.raises(GraphPlanContractError, match="coverage_missing"):
        GraphRetrievalPlanValidator().validate(replace(plan, steps=plan.steps[:1]), context)
    step = replace(plan.steps[0], parameters=(("counterpart_ref", "entity-2"), ("direction", "outgoing")))
    with pytest.raises(GraphPlanContractError, match="step_binding_mismatch"):
        GraphRetrievalPlanValidator().validate(replace(plan, steps=(step, *plan.steps[1:])), context)


@pytest.mark.parametrize("key,value", [("direction", "outgoing"), ("counterpart_ref", "entity-2"), ("id", "invented")])
def test_planner_cannot_write_code_owned_fields(key, value):
    request, _ = bound([Query("pair", "incoming", "entity-1")])
    step = draft()
    step["parameters"][key] = value
    with pytest.raises(GraphPlanContractError, match="draft_keys_invalid"):
        compile_graph_query_plan({"version": "graph-draft.v2", "steps": [step]}, request)


def test_expansion_limit_and_missing_requirement_are_fail_closed():
    queries = [Query("pair", "bidirectional", "entity-1"), Query("pair", "bidirectional", "entity-1")]
    with pytest.raises(GraphPlanContractError, match="step_limit"):
        compile_plan(queries, [draft(), draft(requirement=2)])
    with pytest.raises(GraphPlanContractError, match="coverage_missing"):
        compile_plan(queries, [draft()])


@pytest.mark.parametrize("direction", ["incoming", "outgoing"])
def test_empty_collection_finishes_without_inventing_a_target(direction):
    plan, context = compile_plan([Query("collection", direction), Query("pair", direction, result_of=1)],
                                [draft("rank_related_characters", ranking="positive", limit=1), draft(requirement=2)])
    recall = _FakeRecall(empty=True)
    execution = GraphRetrievalPlanExecutor(recall).execute(plan, context)
    assert len(recall.queries) == 1
    assert recall.queries[0].counterpart_world_character_id is None
    assert execution.steps[1].dependency_short_circuited


@pytest.mark.parametrize("kind,operation,params", [
    ("shared", "shared_neighbors", {}), ("path", "shortest_path", {"max_hops": 3})])
def test_shared_and_path_either_do_not_inherit_legacy_direct_pair_direction(kind, operation, params):
    plan, context = compile_plan([Query(kind, "either", "entity-1")], [draft(operation, **params)])
    result = GraphRetrievalPlanValidator().validate(plan, context)
    assert dict(result.plan.steps[0].parameters)["direction"] == "either"


def test_person_aliases_and_query_meaning_are_in_semantic_hash_and_tool_receipt():
    intent = select(arguments())
    assert intent.version == "retrieval-intent.v2"
    assert intent.entities[0].ref == "entity-1"
    assert intent.graph_queries[0].target_ref == "entity-1"
    assert intent.envelope_hash != select(arguments(direction="outgoing")).envelope_hash
    calls = effective_calls("request", intent, (SelectionToolCall("original", "GRAPH", "{}"),))
    assert calls[0].call_id == "original"
    assert calls[0].arguments()["graph_queries"] == [q.payload() for q in intent.graph_queries]
    assert "ref" not in model_arguments_schema(OPTIONS)["properties"]["entities"]["items"]["properties"]


@pytest.mark.parametrize("person", [{"kind": "mention", "index": 2}, {"kind": "requester_character", "index": 1},
                                  {"kind": "responding_character", "index": None}, {"kind": "unknown", "index": None}])
def test_invalid_or_self_targets_are_rejected(person):
    args = arguments()
    args["graph_queries"][0]["target"] = person
    with pytest.raises((RetrievalContractError, GraphPlanContractError)):
        select(args)


def test_unknown_collection_counterpart_is_never_required():
    args = arguments("collection", "incoming")
    args["entities"] = []
    assert select(args).graph_queries == (Query("collection", "incoming"),)


def test_both_preserves_complete_graph_meaning_and_original_canonical_pair():
    args = arguments(direction="bidirectional")
    args["intent"] = "mixed_evidence"
    args["relationship"] = {"perspective": "responding_character", "from": {"kind": "responding_character", "index": None},
                            "to": {"kind": "mention", "index": 1}, "dimension": None, "requested_polarity": None}
    intent = select(args, ("CANONICAL", "GRAPH"))
    assert intent.relationship.from_ref == "responding_character"
    assert intent.relationship.to_ref == "entity-1"
    assert intent.graph_queries[0].direction == "bidirectional"


def test_legacy_default_schema_remains_unchanged():
    assert "graph_queries" not in model_arguments_schema()["properties"]
    with pytest.raises(ValueError):
        SelectionArgumentOptions(positional_entity_refs=True, graph_query_contract=True)


@pytest.mark.parametrize("recipe,meaning", [("INDEPENDENT_PARALLEL", "mixed_evidence"),
    ("GRAPH_THEN_CANONICAL", "relationship_cause"), ("CANONICAL_THEN_GRAPH", "historical_recall")])
@pytest.mark.parametrize("empty", [False, True])
def test_all_both_recipes_reach_real_toolnode_and_preserve_receipts(recipe, meaning, empty):
    from chat import test_p8_l_n_both_workflow_coordinator as both
    from app.runtime.chat.retrieval_tools import RetrievalToolExecution, ToolPlanningService, ToolBothCoordinator, active_tool_execution, parallel_tools
    async def run():
        _, old = both._resolved(intent_name=meaning, hint=recipe)
        args = arguments(direction="outgoing")
        args["intent"] = meaning
        intent = select(args, ("CANONICAL", "GRAPH"))
        resolved = replace(old, intent_hash=intent.envelope_hash, intent_version=intent.version, version="resolved-retrieval.v2")
        coordinator, canonical, graph = both._coordinator(resolved, canonical_recall=both._CanonicalRecall(empty=empty), graph_recall=both._GraphRecall(empty=empty))
        coordinator._canonical = ToolPlanningService("CANONICAL", coordinator._canonical)
        coordinator._graph = ToolPlanningService("GRAPH", coordinator._graph)
        coordinator._parallel_runner = parallel_tools
        calls = tuple(SelectionToolCall(f"original-{name}", name, json.dumps(args)) for name in ("CANONICAL", "GRAPH"))
        execution = RetrievalToolExecution()
        execution.bind(SimpleNamespace(intent=intent, resolved=resolved, proposed_tool_calls=calls), SimpleNamespace(assert_active=lambda state: None), {})
        token = active_tool_execution.set(execution)
        try:
            value = await ToolBothCoordinator(coordinator).coordinate(both._command(intent, resolved), now=both.NOW, deadline_at=both.DEADLINE)
            execution.assert_complete()
            assert value.selection.selected.value == recipe
            assert value.metrics.coordinator_llm_calls == 0
            assert all(receipt.call.call_id == f"original-{name}" for name, receipt in execution.receipts.items())
            assert all(receipt.call.arguments()["graph_queries"] == [q.payload() for q in intent.graph_queries] for receipt in execution.receipts.values())
        finally:
            active_tool_execution.reset(token)
    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["unique", "missing", "duplicate", "hidden", "blocked"])
def test_typed_selectors_still_require_scoped_resolution(outcome):
    from datetime import datetime, UTC, timedelta
    from chat import test_p8_l_k_retrieval_router as routing
    from app.domains.chat.service.retrieval_routing import RetrievalRoutingService
    intent = select(arguments())
    candidates = () if outcome == "missing" else (routing._candidate("safe-id", visible=outcome != "hidden", blocked=outcome == "blocked"),)
    if outcome == "duplicate":
        candidates += (routing._candidate("second-id"),)
    policy = routing._FakePolicy((routing.RetrievalEntityResolution("entity-1", candidates),))
    now = datetime.now(UTC)
    result = asyncio.run(RetrievalRoutingService(router=routing._FakeRouter(intent), policy=policy).route(routing._command(), now=now, deadline_at=now+timedelta(seconds=20)))
    assert result.intent.route.value == ("GRAPH" if outcome == "unique" else "CLARIFICATION")
    assert result.resolved.world_id == "world-1"
    assert result.resolved.intent_hash == result.intent.envelope_hash


def test_builtin_requester_is_bound_by_code_not_model_ids():
    args = arguments()
    args["entities"] = []
    args["graph_queries"][0]["target"] = {"kind": "requester_character", "index": None}
    intent = select(args)
    assert intent.graph_queries[0].target_ref == "builtin-requester"
    plan, context = compile_plan([Query("pair", "incoming", "entity-1")], [draft()])
    context = replace(context, graph_queries=intent.graph_queries, entity_bindings=(("builtin-requester", "requester-id"),))
    request = GraphPlannerRequest(context.request_id, context.envelope_version, context.envelope_hash,
                                  "fixture", "relationship_state", graph_queries=intent.graph_queries)
    plan = compile_graph_query_plan({"version": "graph-draft.v2", "steps": [draft()]}, request)
    recall = _FakeRecall()
    GraphRetrievalPlanExecutor(recall).execute(plan, context)
    assert recall.queries[0].counterpart_world_character_id == "requester-id"


def test_incoming_rank_uses_observed_incoming_edges_and_returns_actor_for_dependency():
    from test_p8_l_i_graph_recall import _gateway_with, _hit, _scope, SUBJECT_ID, COUNTERPART_ID, NEIGHBOR_ID
    from app.domains.relationships.service.graph_recall import GraphRecallService
    from app.domains.relationships.contracts.graph_recall import GraphRecallQuery, GraphRecallOperation, GraphRecallDirection
    outgoing = _hit(SUBJECT_ID, COUNTERPART_ID, affinity=99)
    incoming = _hit(COUNTERPART_ID, SUBJECT_ID, affinity=4)
    hidden = _hit(NEIGHBOR_ID, SUBJECT_ID, affinity=100)
    _, gateway = _gateway_with(outgoing, incoming, hidden)
    gateway.observed_by_state[hidden.relationship_state_id] = False
    query = GraphRecallQuery(GraphRecallOperation.RANK_RELATED_CHARACTERS, _scope(), direction=GraphRecallDirection.INCOMING,
                             limit=1, enforce_collection_direction=True)
    result = GraphRecallService(gateway).execute(query)
    assert result.world_character_ids == (COUNTERPART_ID,)
    assert result.relationships[0].affinity == 4
    assert result.reason_code == "incoming_rank_bounded_canonical"
    assert result.source.value == "canonical_fallback"


@pytest.mark.parametrize("direction,actor", [("incoming", "other"), ("outgoing", "self")])
def test_neighborhood_direction_is_preserved_without_changing_legacy_default(direction, actor):
    from app.domains.relationships.policies.graph_recall import _bounded_neighborhood
    from app.domains.relationships.contracts.graph_recall import GraphRecallDirection, GraphRecallRelationship
    edges = tuple(GraphRecallRelationship(f"edge-{a}", "world", a, b, 1, 2, 3, 0, 1, 1)
                  for a, b in (("self", "other"), ("other", "self")))
    selected, _ = _bounded_neighborhood("self", edges, depth=1, direction=GraphRecallDirection(direction))
    assert len(selected) == 1 and selected[0].actor_world_character_id == actor
    assert len(_bounded_neighborhood("self", edges, depth=1)[0]) == 2
