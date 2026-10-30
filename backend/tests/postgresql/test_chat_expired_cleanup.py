"""Real PostgreSQL expiry cleanup keeps CAS, atomicity and no output effects."""
from datetime import UTC, datetime, timedelta
from dataclasses import replace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.chat import models
from app.domains.chat.contracts.generation_lifecycle import (
    GenerationContractError, GenerationEvent, GenerationEventType, GenerationFence,
    ResponseRequestState, ResponseTerminalReason,
)
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.runtime.chat.generation_workflows import SqlAlchemyResponseWorkflowUnitOfWork
from postgresql.test_activity_transactions import store
from postgresql.test_chat_lifecycle_snapshot import _requests


@pytest.mark.parametrize('cancelled', [False, True])
def test_expired_attempt_can_only_settle_its_own_failure(store, cancelled):
    engine, _, _ = store
    _requests(engine)
    with Session(engine) as db:
        repository = SqlAlchemyResponseLifecycleRepository(db)
        uow = SqlAlchemyResponseWorkflowUnitOfWork(db)
        record = uow.run_lifecycle_unit(lambda: repository.acquire_lease(request_id='request-one',
            lease_token='owned', now=datetime.now(UTC), lease_expires_at=datetime.now(UTC)+timedelta(minutes=2)))
        fence = GenerationFence(record.request_id, record.thread_id, record.request_scope_hash,
            record.generation_id, record.attempt_number, record.lease_generation, record.state)
        after = record.deadline_at + timedelta(seconds=1)
        event = GenerationEvent(record.request_id, record.request_scope_hash, record.generation_id,
            record.attempt_number, 0, GenerationEventType.CANCELLED if cancelled else GenerationEventType.FAILED,
            {'reason':'client_disconnected'} if cancelled else {'failure_class':'deadline_exceeded','retryable':True})
        # An expiry cannot authorize a later worker to settle another generation.
        with pytest.raises(GenerationContractError, match='fence'):
            uow.run_lifecycle_unit(lambda: repository.accept_event(
                replace(fence, lease_generation=fence.lease_generation+1),event,now=after))
        def settle():
            repository.accept_event(fence,event,now=after)
            return repository.mark_terminal(fence,
                target=ResponseRequestState.CANCELLED if cancelled else ResponseRequestState.TIMED_OUT,
                reason=ResponseTerminalReason.USER_CANCELLED if cancelled else ResponseTerminalReason.DEADLINE_EXCEEDED,
                retryable=True, now=after)
        saved=uow.run_lifecycle_unit(settle)
        assert saved.last_emitted_sequence==0
        assert saved.state is (ResponseRequestState.CANCELLED if cancelled else ResponseRequestState.TIMED_OUT)
        assert saved.lease_token is None and saved.committed_assistant_message_id is None
        with pytest.raises(GenerationContractError):
            uow.run_lifecycle_unit(settle)
        assert db.scalar(select(func.count()).select_from(models.MessageMessage).where(models.MessageMessage.role=='assistant'))==0
    assert engine.pool.checkedout()==0
