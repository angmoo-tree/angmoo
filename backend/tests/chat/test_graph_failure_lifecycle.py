"""Graph diagnostics and manual retry through the real lifecycle and Chat API service."""
import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.contracts.retrieval_observation import Observation, current
from app.domains.chat.contracts.call_tracker import restore_call_tracker_snapshot, LlmNode
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from app.domains.chat.contracts.generation_lifecycle import GenerationEventType
from app.domains.chat.exceptions import MessageServiceError
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat import test_p8_l_m_graph_retrieval_planner as g


def fail_request(session, *, code="JSONDecodeError", detailed=False):
    class RepairedRouter(f._Router):
        async def route(self, *args, **kwargs):
            result = await super().route(*args, **kwargs)
            tracker = restore_call_tracker_snapshot(result.call_tracker, deadline_at=kwargs["deadline_at"])
            tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=kwargs["now"], repair=True)
            tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=kwargs["now"])
            return replace(result, resolved=replace(result.resolved, canonical_operation_allowlist=()), call_tracker=tracker.snapshot())
    record = f._request(session, RetrievalRoute.GRAPH)
    session.commit()
    generator = f._Generator()
    workflow = f._workflow(session, RetrievalRoute.GRAPH, generator, router=RepairedRouter(RetrievalRoute.GRAPH))
    planner = g._FakePlanner(g.GraphPlannerOutputError(code, physical_attempt_count=2))
    recall = g._FakeRecall()
    workflow._graph = g.GraphRetrievalPlanningService(planner=planner, executor=g.GraphRetrievalPlanExecutor(recall))
    token = current.set(Observation(detailed=detailed))
    try: events = asyncio.run(f._collect(workflow.run(f._command(record))))
    finally: current.reset(token)
    failed = SqlAlchemyResponseLifecycleRepository(session).get_request(record.request_id)
    assert not generator.requests and not recall.queries and len(planner.requests) == 1
    return failed, events, workflow


@pytest.mark.parametrize("detailed", [False, True])
@pytest.mark.parametrize("code,retryable", [
    ("JSONDecodeError", True), ("graph_plan_direction_required", True),
    ("graph_plan_binding_mismatch", False), ("private-unknown", False),
])
def test_graph_error_is_durable_counted_safe_and_consistent_on_reconnect(response_session, detailed, code, retryable):
    failed, events, workflow = fail_request(response_session, code=code, detailed=detailed)
    assert events[-1].event_type is GenerationEventType.FAILED
    assert events[-1].payload == {"failure_class": "retrieval_rejected", "retryable": retryable}
    assert failed.retryable is retryable
    assert failed.call_tracker["logical_total"] == 3
    assert failed.call_tracker["physical_counts"]["graph_planner"] == 2
    assert failed.call_tracker["physical_total"] == 4
    assert failed.call_tracker["logical_counts"]["character_response_generator"] == 0
    diagnostic = failed.node_state["graph_diagnostic"]
    assert diagnostic["terminal_code"] == "graph_planner_request_wide_repair_exhausted"
    assert diagnostic["rejections"][0]["validation_code"] == ("unknown" if code == "private-unknown" else code)
    assert len(json.dumps(diagnostic).encode()) < 2048
    assert "private" not in json.dumps(diagnostic)
    owner = response_session.get(f.models.User, "p-owner")
    status = f.generation_service.get_world_response_request(response_session, owner, "p-world", "p-thread", failed.request_id)
    assert status.retryable is retryable and status.failure_class == "retrieval_rejected"
    assert "graph_diagnostic" not in status.model_dump_json()
    replay = asyncio.run(f._collect(workflow.run(f._command(failed))))
    assert replay[-1].payload == events[-1].payload
    assert response_session.scalar(select(func.count(f.models.MessageMessage.id)).where(f.models.MessageMessage.role == "assistant")) == 0


def test_graph_retry_is_explicit_idempotent_and_reuses_slot_and_user_message(response_session):
    failed, _, _ = fail_request(response_session)
    owner = response_session.get(f.models.User, "p-owner")
    before = response_session.scalar(select(func.count(f.models.MessageMessage.id)))
    data = f.WorldChatRetryCreate(failed_request_id=failed.request_id, idempotency_key="graph-manual-retry")
    accepted = f.generation_service.retry_world_response(response_session, owner, "p-world", "p-thread", data)
    replay = f.generation_service.retry_world_response(response_session, owner, "p-world", "p-thread", data)
    request = accepted.response_request
    assert replay.outcome == "replayed" and replay.response_request.request_id == request.request_id
    assert request.request_id != failed.request_id and request.generation_id != failed.generation_id
    assert request.response_slot_id == failed.response_slot_id
    assert request.attempt_number == failed.attempt_number + 1
    assert accepted.user_message.id == failed.user_message_id
    assert response_session.scalar(select(func.count(f.models.MessageMessage.id))) == before
    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    new_record = repository.get_request(request.request_id)
    assert new_record.retry_of_request_id == failed.request_id
    assert new_record.call_tracker == {}  # New attempt starts through normal selection.
    assert repository.get_request(failed.request_id).call_tracker == failed.call_tracker
    with pytest.raises(MessageServiceError):
        f.generation_service.retry_world_response(response_session, owner, "p-world", "p-thread",
            f.WorldChatRetryCreate(failed_request_id=failed.request_id, idempotency_key="different-retry-key"))
    events = asyncio.run(f._collect(f._workflow(response_session, RetrievalRoute.CURRENT_CONTEXT, f._Generator()).run(f._command(new_record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED
    with pytest.raises(MessageServiceError):
        f.generation_service.retry_world_response(response_session, owner, "p-world", "p-thread",
            f.WorldChatRetryCreate(failed_request_id=request.request_id, idempotency_key="committed-retry-key"))


@pytest.mark.parametrize("guard", ["foreign_world", "foreign_owner", "new_user", "nonretryable"])
def test_graph_retry_does_not_bypass_existing_scope_or_latest_message_guards(response_session, guard):
    failed, _, _ = fail_request(response_session, code="unknown" if guard == "nonretryable" else "JSONDecodeError")
    owner = response_session.get(f.models.User, "p-owner")
    world = "foreign-world" if guard == "foreign_world" else "p-world"
    if guard == "foreign_owner":
        owner = f.models.User(id="foreign-owner", email="foreign@fixture.test")
    if guard == "new_user":
        response_session.add(f.models.MessageMessage(thread_id="p-thread", role="user", content="synthetic later message", status="ok", created_at=datetime.now(UTC)))
        response_session.commit()
    with pytest.raises(MessageServiceError):
        f.generation_service.retry_world_response(response_session, owner, world, "p-thread",
            f.WorldChatRetryCreate(failed_request_id=failed.request_id, idempotency_key="guarded-retry-key"))


def test_invalid_optional_diagnostic_is_ignored_without_losing_terminal_record(response_session):
    from app.domains.chat.contracts.generation_lifecycle import GenerationFence, ResponseRequestState, ResponseTerminalReason
    from datetime import timedelta
    record = f._request(response_session, RetrievalRoute.CURRENT_CONTEXT)
    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    now = datetime.now(UTC)
    record = repository.acquire_lease(request_id=record.request_id, lease_token="fixture", now=now, lease_expires_at=now + timedelta(seconds=30))
    failed = repository.mark_terminal(GenerationFence(request_id=record.request_id, thread_id=record.thread_id,
        request_scope_hash=record.request_scope_hash, generation_id=record.generation_id,
        attempt_number=record.attempt_number, lease_generation=record.lease_generation, expected_prior_state=record.state),
        target=ResponseRequestState.FAILED, reason=ResponseTerminalReason.RETRIEVAL_FAILURE, retryable=False,
        failure_class="retrieval_rejected", graph_diagnostic={"private": "secret"}, now=now)
    assert failed.node_state == {"failure_class": "retrieval_rejected"}
    assert failed.retryable is False


def test_cancelled_graph_workflow_persists_dispatches_without_assistant_commit(response_session):
    from app.domains.relationships.contracts.graph_diagnostics import GraphAttemptObservation
    async def run():
        entered = asyncio.Event()
        class Router(f._Router):
            async def route(self, *args, **kwargs):
                routed = await super().route(*args, **kwargs)
                return replace(routed, resolved=replace(routed.resolved, canonical_operation_allowlist=()))
        class Planner:
            async def plan(self, request):
                entered.set()
                try: await asyncio.Event().wait()
                except asyncio.CancelledError as exc:
                    exc.graph_attempt = GraphAttemptObservation(1)
                    raise
        record = f._request(response_session, RetrievalRoute.GRAPH)
        response_session.commit()
        generator = f._Generator()
        workflow = f._workflow(response_session, RetrievalRoute.GRAPH, generator, router=Router(RetrievalRoute.GRAPH))
        workflow._graph = g.GraphRetrievalPlanningService(planner=Planner(), executor=g.GraphRetrievalPlanExecutor(g._FakeRecall()))
        task = asyncio.create_task(f._collect(workflow.run(f._command(record))))
        await asyncio.wait_for(entered.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        stored = SqlAlchemyResponseLifecycleRepository(response_session).get_request(record.request_id)
        assert stored.state is f.ResponseRequestState.CANCELLED
        assert stored.call_tracker["physical_counts"]["graph_planner"] == 1
        assert stored.node_state["graph_diagnostic"]["terminal_code"] == "graph_retrieval_cancelled"
        assert not generator.requests and stored.committed_assistant_message_id is None
    asyncio.run(run())
