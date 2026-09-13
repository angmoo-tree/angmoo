"""Actual graph execution must preserve budgets, scope and durable outcomes."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from app.contracts.retrieval_observation import current
from app.domains.chat.contracts.generation_lifecycle import (
    GenerationEventType,
    ResponseRequestState,
)
from app.domains.chat.contracts.response_execution import (
    ResponseAction,
    ResponseExecutionError,
    ResponsePhase,
    initial_response_state,
)
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from app.domains.chat.models import ChatRetrievalDiagnostic
from app.domains.chat.policies import select_response_action
from app.runtime.chat.generation_workflows import SupervisorResponseWorkflowUnitOfWork
from app.runtime.chat.response_graph import (
    LangGraphResponseExecutor,
    compiled_response_graph,
)
from chat.test_p8_l_p_evidence_response_streaming import (
    _collect,
    _command,
    _Generator,
    _request,
    _Router,
    _workflow,
    response_session,
)
from model_fixture_support import models
from sqlalchemy import func, select


class RecordingExecutor(LangGraphResponseExecutor):
    async def run(self, state, steps):
        try:
            return await super().run(state, steps)
        finally:
            self.observation = current.get().payload()
            self.steps = steps


@pytest.mark.parametrize("waiting_at", ["router", "canonical", "crg"])
def test_cancellation_reaches_inflight_graph_worker(response_session, waiting_at):
    record = _request(response_session, RetrievalRoute.CANONICAL)
    response_session.commit()
    generator = _Generator()
    workflow = _workflow(response_session, RetrievalRoute.CANONICAL, generator)
    entered, stopped = asyncio.Event(), asyncio.Event()

    async def blocking(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    if waiting_at == "router":
        workflow._router.route = blocking
    elif waiting_at == "canonical":
        workflow._canonical.plan_and_execute = blocking
    else:
        generator.generate = blocking

    async def cancel_inflight():
        task = asyncio.create_task(_collect(workflow.run(_command(record))))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()

    asyncio.run(cancel_inflight())
    stored = workflow._lifecycle.get_request(record.request_id)
    assert stored.state is ResponseRequestState.CANCELLED
    assert stored.committed_assistant_message_id is None
    assert current.get() is None


@pytest.mark.parametrize(
    "route,branch,calls,commits",
    [
        (RetrievalRoute.CURRENT_CONTEXT, "current_context", 2, 12),
        (RetrievalRoute.CANONICAL, "canonical_retrieval", 3, 13),
        (RetrievalRoute.GRAPH, "graph_retrieval", 3, 13),
        (RetrievalRoute.BOTH, "both_retrieval", 4, 13),
        (RetrievalRoute.CLARIFICATION, "clarification", 2, 12),
    ],
)
def test_compiled_routes_preserve_calls_commits_and_supervisor_visits(
    response_session, route, branch, calls, commits
):
    record = _request(response_session, route)
    response_session.commit()
    generator = _Generator()
    workflow = _workflow(response_session, route, generator)
    executor = RecordingExecutor()
    workflow._graph_executor = executor
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED
    decisions = [
        e for e in executor.observation["events"] if e["event"] == "supervisor"
    ]
    assert [e["operation"] for e in decisions] == [
        "route_and_resolve",
        branch,
        "freeze_evidence",
        "generate_response",
        "end",
    ]
    assert [e["step"] for e in decisions] == [1, 2, 3, 4, 5]
    assert workflow._unit_of_work.commits == commits
    stored = workflow._lifecycle.get_request(record.request_id)
    assert stored.call_tracker["logical_total"] == calls
    assert stored.call_tracker["physical_total"] == calls
    assert len(generator.requests) == 1
    assert current.get() is None


def test_graph_has_no_independent_router_node_or_checkpointing():
    graph = compiled_response_graph()
    assert set(graph.nodes) - {"__start__"} == {"supervisor"} | {
        a.value for a in ResponseAction if a not in {ResponseAction.END, ResponseAction.ROUTE}
    }
    assert graph.checkpointer is None


def test_runtime_diagnostics_persist_five_decisions_without_extra_commits(
    response_session,
    monkeypatch,
):
    from app.domains.chat.repository import retrieval_diagnostics

    save = retrieval_diagnostics.save
    diagnostic_writes = 0

    def counted_save(*args):
        nonlocal diagnostic_writes
        diagnostic_writes += 1
        return save(*args)

    monkeypatch.setattr(retrieval_diagnostics, "save", counted_save)
    record = _request(response_session, RetrievalRoute.CURRENT_CONTEXT)
    response_session.commit()
    workflow = _workflow(response_session, RetrievalRoute.CURRENT_CONTEXT, _Generator())
    uow = SupervisorResponseWorkflowUnitOfWork(response_session)
    checkpoint = uow.checkpoint
    commits = 0

    def count_checkpoint():
        nonlocal commits
        checkpoint()
        commits += 1

    uow.checkpoint = count_checkpoint
    workflow._unit_of_work = uow
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED
    assert commits == 12
    assert diagnostic_writes == 4  # request, router result, CRG input/result
    row = response_session.get(ChatRetrievalDiagnostic, record.request_id)
    payload = json.loads(row.payload_json)
    assert row.payload_bytes <= 16384
    assert [
        e["operation"] for e in payload["events"] if e["event"] == "supervisor"
    ] == [
        "route_and_resolve",
        "current_context",
        "freeze_evidence",
        "generate_response",
        "end",
    ]
    assert any(e["event"] == "crg_completed" for e in payload["events"])


@pytest.mark.parametrize(
    "patch",
    [
        {"visits": -1},
        {"visits": True},
        {"visits": 5},
        {"visits": 500},
        {"phase": "unknown"},
        {"phase": ResponsePhase.COMPLETE, "visits": 4},
        {"phase": ResponsePhase.EVIDENCE, "visits": 2},
        {"response": object()},
        {"action": ResponseAction.GENERATE},
    ],
)
def test_impossible_state_is_rejected_instead_of_skipping_work(patch):
    state = initial_response_state(
        SimpleNamespace(request_id="fixture", request_scope_hash="scope")
    )
    with pytest.raises(ResponseExecutionError):
        select_response_action({**state, **patch})


class AfterStepExecutor(LangGraphResponseExecutor):
    def __init__(self, action, callback):
        self.action, self.callback = action, callback

    async def run(self, state, steps):
        execute = steps.execute

        async def intercept(action, value):
            result = await execute(action, value)
            if action is self.action:
                return await self.callback(steps, action, value, result)
            return result

        steps.execute = intercept
        return await super().run(state, steps)


@pytest.mark.parametrize(
    "action,expected_calls",
    [
        (ResponseAction.ROUTE, 1),
        (ResponseAction.FREEZE, 2),
        (ResponseAction.GENERATE, 3),
    ],
)
def test_failure_after_worker_commit_preserves_latest_fence_and_calls(
    response_session, action, expected_calls
):
    async def crash(*args):
        raise RuntimeError("fixture_worker_failure")

    record = _request(response_session, RetrievalRoute.CANONICAL)
    response_session.commit()
    generator = _Generator()
    workflow = _workflow(response_session, RetrievalRoute.CANONICAL, generator)
    workflow._graph_executor = AfterStepExecutor(action, crash)
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.FAILED
    stored = workflow._lifecycle.get_request(record.request_id)
    assert stored.state is ResponseRequestState.FAILED
    assert stored.call_tracker["logical_total"] == expected_calls
    assert stored.call_tracker["physical_total"] == expected_calls
    assert stored.committed_assistant_message_id is None
    assert len(generator.requests) == (1 if action is ResponseAction.GENERATE else 0)


@pytest.mark.parametrize(
    "mode", ["missing_result", "foreign_scope", "duplicate_worker", "early_end"]
)
def test_corrupt_graph_output_cannot_generate_or_commit(response_session, mode):
    async def corrupt(steps, action, before, result):
        if mode == "missing_result":
            return {**result, "routing": None}
        if mode == "foreign_scope":
            return {**result, "request_scope_hash": "foreign"}
        if mode == "early_end":
            return {**result, "phase": ResponsePhase.COMPLETE}
        # Even a miswired edge cannot replay an already executed worker.
        return await steps.execute(action, before)

    record = _request(response_session, RetrievalRoute.CANONICAL)
    response_session.commit()
    generator = _Generator()
    workflow = _workflow(response_session, RetrievalRoute.CANONICAL, generator)
    workflow._graph_executor = AfterStepExecutor(ResponseAction.ROUTE, corrupt)
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].payload == {
        "failure_class": "generation_conflict",
        "retryable": False,
    }
    assert len(generator.requests) == 0
    assert (
        workflow._lifecycle.get_request(record.request_id).state
        is ResponseRequestState.FAILED
    )


@pytest.mark.parametrize(
    "action", [ResponseAction.ROUTE, ResponseAction.FREEZE, ResponseAction.GENERATE]
)
def test_cancel_after_worker_commit_does_not_leave_active_attempt(
    response_session, action
):
    async def cancel(*args):
        raise asyncio.CancelledError()

    record = _request(response_session, RetrievalRoute.CURRENT_CONTEXT)
    response_session.commit()
    generator = _Generator()
    workflow = _workflow(response_session, RetrievalRoute.CURRENT_CONTEXT, generator)
    workflow._graph_executor = AfterStepExecutor(action, cancel)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_collect(workflow.run(_command(record))))
    stored = workflow._lifecycle.get_request(record.request_id)
    assert stored.state is ResponseRequestState.CANCELLED
    assert stored.committed_assistant_message_id is None
    if action is ResponseAction.GENERATE:
        assert stored.call_tracker["physical_total"] == 2
    assert current.get() is None


@pytest.mark.parametrize("after_commit", [False, True])
def test_failed_crg_reservation_commit_does_not_call_provider(
    response_session, after_commit
):
    record = _request(response_session, RetrievalRoute.CURRENT_CONTEXT)
    response_session.commit()
    generator = _Generator()
    workflow = _workflow(response_session, RetrievalRoute.CURRENT_CONTEXT, generator)
    checkpoint = workflow._unit_of_work.checkpoint
    failed = False

    def fail_once():
        nonlocal failed
        if (
            not failed
            and workflow._lifecycle.get_request(record.request_id).state
            is ResponseRequestState.RESPONSE_GENERATING
        ):
            failed = True
            if after_commit:
                checkpoint()
            raise OSError("fixture_commit_failure")
        checkpoint()

    workflow._unit_of_work.checkpoint = fail_once
    events = asyncio.run(_collect(workflow.run(_command(record))))
    stored = workflow._lifecycle.get_request(record.request_id)
    assert events[-1].event_type is GenerationEventType.FAILED
    assert stored.state is ResponseRequestState.FAILED
    assert stored.call_tracker["logical_total"] == 2  # reservation retained
    assert stored.call_tracker["physical_total"] == 1
    assert generator.requests == []


def test_recursion_exhaustion_is_failed_not_success(response_session, monkeypatch):
    from app.runtime.chat import response_graph

    graph = compiled_response_graph()

    class SmallLimit:
        async def ainvoke(self, state, *, context, config):
            return await graph.ainvoke(
                state, context=context, config={"recursion_limit": 1}
            )

    monkeypatch.setattr(response_graph, "compiled_response_graph", lambda: SmallLimit())
    record = _request(response_session, RetrievalRoute.CURRENT_CONTEXT)
    response_session.commit()
    generator = _Generator()
    workflow = _workflow(response_session, RetrievalRoute.CURRENT_CONTEXT, generator)
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].payload == {
        "failure_class": "generation_conflict",
        "retryable": False,
    }
    assert generator.requests == []
    assert (
        workflow._lifecycle.get_request(record.request_id).state
        is ResponseRequestState.FAILED
    )


def test_shared_graph_keeps_concurrent_request_sessions_and_observers_separate():
    # Separate synthetic databases; no user runtime data or external providers.
    fixture_a, fixture_b = (
        response_session.__wrapped__(),
        response_session.__wrapped__(),
    )
    db_a, db_b = next(fixture_a), next(fixture_b)

    class YieldingRouter(_Router):
        async def route(self, *args, **kwargs):
            await asyncio.sleep(0.001)
            return await super().route(*args, **kwargs)

    async def run_one(db, route):
        record = _request(db, route)
        db.commit()
        generator = _Generator()
        workflow = _workflow(db, route, generator, router=YieldingRouter(route))
        executor = RecordingExecutor()
        workflow._graph_executor = executor
        events = await _collect(workflow.run(_command(record)))
        assert events[-1].event_type is GenerationEventType.COMPLETED
        assert len(generator.requests) == 1
        assert generator.requests[0].evidence.request_id == record.request_id
        assert executor.steps.progress.record.request_id == record.request_id
        assert (
            db.scalar(
                select(func.count(models.MessageMessage.id)).where(
                    models.MessageMessage.role == "assistant"
                )
            )
            == 1
        )
        return executor.observation

    async def run_both():
        return await asyncio.gather(
            run_one(db_a, RetrievalRoute.CURRENT_CONTEXT),
            run_one(db_b, RetrievalRoute.CANONICAL),
        )

    try:
        a, b = asyncio.run(run_both())

        def operations(obs):
            return [e["operation"] for e in obs["events"] if e["event"] == "supervisor"]

        assert operations(a)[1] == "current_context"
        assert operations(b)[1] == "canonical_retrieval"
        assert current.get() is None
    finally:
        fixture_a.close()
        fixture_b.close()
