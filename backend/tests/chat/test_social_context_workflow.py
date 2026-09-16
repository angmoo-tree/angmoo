import asyncio
from dataclasses import replace
import json

import pytest

from app.domains.chat.contracts.generation_lifecycle import GenerationEventType
from app.domains.chat.contracts.recall_mode import ChatRecallMode
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError, RetrievalRoute
from app.domains.chat.contracts.supervisor_selection import SelectionArgumentOptions, parse_control_selection
from app.domains.relationships.contracts.graph_recall import GraphRecallResult, GraphRecallSource, GraphRecallStatus
from app.domains.relationships.contracts.social_context import SocialContextChangedError
from app.domains.relationships.service.social_context import SocialContextService
from app.integrations.llm.supervisor_selection import control_selection_tools
from chat.test_supervisor_control_tools import native
from chat.test_p8_l_p_evidence_response_streaming import (
    _collect, _command, _Generator, _request, _Router, _workflow, response_session,
)


class SnapshotProvider:
    def __init__(self):
        self.snapshot = None
        self.validations = 0
        self.changed = False

    def prepare(self, scope, *, counterpart_id=None):
        self.snapshot = SocialContextService(lambda q: GraphRecallResult(
            q.operation, GraphRecallStatus.READY, GraphRecallSource.GRAPH,
        )).prepare(scope, labels={}, counterpart_id=counterpart_id)
        return self.snapshot

    def assert_current(self, snapshot):
        assert snapshot is self.snapshot
        self.validations += 1
        if self.changed:
            raise SocialContextChangedError("social_context_changed")


class SocialRouter(_Router):
    async def route(self, *args, social_snapshot=None, **kwargs):
        self.snapshot = social_snapshot
        return await super().route(*args, **kwargs)


@pytest.mark.parametrize("route", [RetrievalRoute.CURRENT_CONTEXT, RetrievalRoute.CANONICAL, RetrievalRoute.CLARIFICATION])
def test_identical_snapshot_reaches_both_consumers_without_preparation_ai(response_session, route):
    record = _request(response_session, route)
    response_session.commit()
    generator, router, snapshots = _Generator(), SocialRouter(route), SnapshotProvider()
    workflow = _workflow(response_session, route, generator, router=router)
    workflow._recall_mode = ChatRecallMode.SOCIAL_BASELINE
    workflow._social_context_provider = snapshots
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED
    assert router.snapshot is generator.requests[0].social_snapshot is snapshots.snapshot
    assert snapshots.validations == 3
    stored = workflow._lifecycle.get_request(record.request_id)
    assert stored.call_tracker["logical_total"] == (3 if route is RetrievalRoute.CANONICAL else 2)
    assert stored.node_state["social_snapshot"]["snapshot_id"] == snapshots.snapshot.snapshot_id


def test_change_during_generation_prevents_first_public_delta(response_session):
    route = RetrievalRoute.CURRENT_CONTEXT
    record = _request(response_session, route)
    response_session.commit()
    generator, snapshots = _Generator(), SnapshotProvider()
    original = generator.generate
    async def generate(request):
        result = await original(request)
        snapshots.changed = True
        return result
    generator.generate = generate
    workflow = _workflow(response_session, route, generator, router=SocialRouter(route))
    workflow._recall_mode = ChatRecallMode.SOCIAL_BASELINE
    workflow._social_context_provider = snapshots
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert GenerationEventType.DELTA not in [e.event_type for e in events]
    assert workflow._lifecycle.get_request(record.request_id).committed_assistant_message_id is None


def test_current_relationship_inspector_is_private_and_not_a_graph_tool_result(response_session):
    from relationships.test_social_context import relationship, result
    class Current(SnapshotProvider):
        def prepare(self, scope, *, counterpart_id=None):
            row = relationship("p-requester", world_id=scope.world_id,
                actor_world_character_id=scope.subject_world_character_id)
            self.snapshot = SocialContextService(lambda q: result(q, [row])).prepare(
                scope, labels={"p-requester": "친구"})
            return self.snapshot
    record = _request(response_session, RetrievalRoute.CURRENT_CONTEXT)
    response_session.commit()
    workflow = _workflow(response_session, RetrievalRoute.CURRENT_CONTEXT, _Generator(), router=SocialRouter(RetrievalRoute.CURRENT_CONTEXT))
    workflow._recall_mode = ChatRecallMode.SOCIAL_BASELINE
    workflow._social_context_provider = Current()
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED
    stored = workflow._lifecycle.get_request(record.request_id)
    assert stored.response_metadata["public_evidence_count"] == 0
    current = stored.response_metadata["_social_context_inspector_v1"]["items"]
    assert len(current) == 1 and current[0]["axes"] == []
    assert current[0]["locator"]["source_revision"] == "1"
    assert current[0]["locator"]["actor_world_character_id"] == "p-responding"
    assert "_social_context_inspector_v1" not in str(events[-1].payload)


@pytest.mark.parametrize("route", [RetrievalRoute.GRAPH, RetrievalRoute.BOTH])
def test_graph_rejected_before_branch_even_with_noncompliant_router(response_session, route):
    record = _request(response_session, route)
    response_session.commit()
    generator = _Generator()
    workflow = _workflow(response_session, route, generator, router=SocialRouter(route))
    workflow._recall_mode = ChatRecallMode.SOCIAL_BASELINE
    workflow._social_context_provider = SnapshotProvider()
    asyncio.run(_collect(workflow.run(_command(record))))
    assert not generator.requests
    assert workflow._lifecycle.get_request(record.request_id).committed_assistant_message_id is None


def test_native_schema_and_parser_share_graph_exclusion():
    options = SelectionArgumentOptions(code_coordination=True, social_context_mode=True)
    assert {t.name for t in control_selection_tools(options)} == {"CANONICAL", "USE_CONTEXT", "REQUEST_CLARIFICATION"}
    call = native(RetrievalRoute.GRAPH)
    args = call.arguments()
    args.pop("coordination_hint")
    with pytest.raises(RetrievalContractError):
        parse_control_selection("", (replace(call, arguments_json=json.dumps(args)),), options=options)


def test_hybrid_search_text_is_required_only_for_canonical_and_bound_to_intent_hash():
    options = SelectionArgumentOptions(code_coordination=True, social_context_mode=True, hybrid_recall=True)
    schemas = {t.name: t.parameters for t in control_selection_tools(options)}
    assert "search_text" in schemas["CANONICAL"]["required"]
    assert "search_text" not in schemas["USE_CONTEXT"]["properties"]
    call = native(RetrievalRoute.CANONICAL)
    args = call.arguments()
    args.pop("coordination_hint")
    args["search_text"] = "합동 훈련에서 지킨 약속"
    call = replace(call, arguments_json=json.dumps(args))
    intent = parse_control_selection("", (call,), options=options)
    assert intent.search_text == args["search_text"]
    assert replace(intent, search_text="different").envelope_hash != intent.envelope_hash
    args.pop("search_text")
    with pytest.raises(RetrievalContractError):
        parse_control_selection("", (replace(call, arguments_json=json.dumps(args)),), options=options)


def test_hybrid_toolnode_completes_with_two_generation_calls_and_no_planner(response_session):
    from app.domains.chat.service.hybrid_canonical import HybridCanonicalService
    from app.runtime.chat.retrieval_tools import ToolPlanningService
    from app.domains.memory.contracts.hybrid_recall import HybridRecallResult, HybridEmbeddingUsage, RecallAxisReceipt, RecallAxisStatus
    class Router(SocialRouter):
        async def route(self, *args, **kwargs):
            result = await super().route(*args, **kwargs)
            intent = replace(result.intent, search_text="훈련 약속")
            resolved = replace(result.resolved, intent_hash=intent.envelope_hash)
            from app.domains.chat.contracts.recall_interpretation import RecallInterpretationContext, text_hash
            interpretation = RecallInterpretationContext(resolved.request_id, intent.envelope_hash,
                resolved.envelope_hash, text_hash(args[0].user_message), intent.search_text,
                (), None, None, "not_requested", "not_requested", None)
            return replace(result, intent=intent, resolved=resolved, interpretation=interpretation, selection_mode="native_control")
    class Hybrid:
        calls = 0
        async def execute(self, request, *, deadline):
            self.calls += 1
            return HybridRecallResult(request.request_id, request.call_id, request.envelope_hash, request.scope,
                RecallAxisStatus.READY, (), tuple(RecallAxisReceipt(axis, RecallAxisStatus.READY, True, 0, 1)
                for axis in ("fts", "vector")), (), HybridEmbeddingUsage(), 0, 0, 2)
    record = _request(response_session, RetrievalRoute.CANONICAL)
    response_session.commit()
    generator, hybrid = _Generator(), Hybrid()
    workflow = _workflow(response_session, RetrievalRoute.CANONICAL, generator, router=Router(RetrievalRoute.CANONICAL))
    workflow._recall_mode = ChatRecallMode.SOCIAL_HYBRID
    workflow._social_context_provider = SnapshotProvider()
    workflow._canonical = ToolPlanningService("CANONICAL", HybridCanonicalService(hybrid))
    from chat.test_response_supervisor import RecordingExecutor
    executor = RecordingExecutor()
    workflow._graph_executor = executor
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED, executor.observation
    stored = workflow._lifecycle.get_request(record.request_id)
    assert stored.call_tracker["logical_total"] == 2
    assert stored.node_state["canonical_metrics"]["planner_logical_calls"] == 0
    assert hybrid.calls == 1 and len(generator.requests) == 1
