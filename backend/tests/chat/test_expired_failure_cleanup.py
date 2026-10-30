"""Expiry blocks output, but must not block the fenced failure/cancel record."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.domains.chat import models
from app.domains.chat.contracts.generation_lifecycle import (
    GenerationContractError, GenerationEventType, ResponseRequestState,
)
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError, RetrievalRoute
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.domains.chat.service import response_workflow
from chat.test_p8_l_p_evidence_response_streaming import (
    _collect, _command, _Generator, _request, _workflow, response_session,
)


def test_provider_deadline_closes_request_without_replaying_or_publishing(response_session, monkeypatch):
    route = RetrievalRoute.CURRENT_CONTEXT
    record = _request(response_session, route)
    response_session.commit()
    generator = _Generator()
    calls = []

    class ExpiredClock:
        @staticmethod
        def now(zone):
            return record.deadline_at + timedelta(seconds=1)

    async def timed_out(request):
        calls.append(request)
        monkeypatch.setattr(response_workflow, 'datetime', ExpiredClock)
        raise RetrievalContractError('llm_request_deadline_exceeded')

    generator.generate = timed_out
    workflow = _workflow(response_session, route, generator)
    outcomes = []
    class DeliveredInput:
        def record_terminal(self, request, state, *, reason):
            outcomes.append((state, reason))
    # Exercise cleanup after an input was recorded, without inventing a new
    # Memory input state for Chat's more specific timeout outcome.
    original_fail = workflow._fail
    async def fail_with_input(*args, **kwargs):
        workflow._situation_memory = DeliveredInput()
        async for event in original_fail(*args, **kwargs):
            yield event
    workflow._fail = fail_with_input
    events = asyncio.run(_collect(workflow.run(_command(record))))
    saved = workflow._lifecycle.get_request(record.request_id)
    assert saved.state is ResponseRequestState.TIMED_OUT
    assert saved.terminal_reason.value == 'deadline_exceeded'
    assert saved.node_state['failure_class'] == 'deadline_exceeded'
    assert saved.lease_token is None and saved.lease_expires_at is None
    assert saved.committed_assistant_message_id is None
    assert [e.event_type for e in events] == [GenerationEventType.ACCEPTED, GenerationEventType.FAILED]
    assert saved.last_emitted_sequence == events[-1].sequence == 1
    assert len(calls) == 1
    assert outcomes == [('failed', 'deadline_exceeded')]
    assert response_session.scalar(select(func.count()).select_from(models.MessageMessage).where(models.MessageMessage.role == 'assistant')) == 0


@pytest.mark.parametrize('event_type', [GenerationEventType.FAILED, GenerationEventType.CANCELLED])
def test_expired_cleanup_keeps_identity_generation_and_sequence_fences(response_session, event_type):
    route = RetrievalRoute.CURRENT_CONTEXT
    record = _request(response_session, route)
    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    record = repository.acquire_lease(request_id=record.request_id, lease_token='owned',
        now=datetime.now(UTC), lease_expires_at=record.deadline_at)
    workflow = _workflow(response_session, route, _Generator())
    fence = workflow._fence(record)
    event = workflow._event(record, event_type, sequence=0, payload=(
        {'failure_class': 'deadline_exceeded', 'retryable': True}
        if event_type is GenerationEventType.FAILED else {'reason': 'client_disconnected'}))
    now = record.deadline_at + timedelta(seconds=1)
    with pytest.raises(GenerationContractError, match='fence'):
        repository.accept_event(replace(fence, lease_generation=fence.lease_generation + 1), event, now=now)
    repository.accept_event(fence, event, now=now)
    assert repository.get_request(record.request_id).last_emitted_sequence == 0
    with pytest.raises(GenerationContractError):
        repository.accept_event(fence, replace(event, sequence=2), now=now)
    for output_type, payload in ((GenerationEventType.DELTA, {'text': 'must not appear'}),
                                 (GenerationEventType.COMPLETED, {})):
        with pytest.raises(GenerationContractError, match='after_deadline'):
            repository.accept_event(fence, replace(event, event_type=output_type, payload=payload, sequence=1), now=now)
