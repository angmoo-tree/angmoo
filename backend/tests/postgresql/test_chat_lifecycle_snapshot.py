"""Request-local CAS updates do not require cross-request SSI dependencies."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.chat.contracts import CreateResponseRequest, build_request_scope_hash
from app.domains.chat.contracts.generation_lifecycle import GenerationContractError
from app.domains.chat.models import MessageMessage
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.runtime.chat.generation_workflows import SqlAlchemyResponseWorkflowUnitOfWork
from postgresql.test_activity_transactions import store
from postgresql.test_chat_admission_concurrency import _independent_threads


def _requests(engine):
    _independent_threads(engine)
    with Session(engine) as db:
        repository = SqlAlchemyResponseLifecycleRepository(db)
        for suffix, actor in [('one', 'social-uow-autonomous-actor'), ('two', 'actor-two')]:
            thread = 'chat-' + suffix
            message = MessageMessage(thread_id=thread, role='user', content='synthetic lifecycle test', status='ok')
            db.add(message)
            db.flush()
            scope = dict(owner_id='social-uow-owner', world_id='social-uow-world', thread_id=thread,
                requester_world_character_id='social-uow-owner-actor', responding_world_character_id=actor)
            repository.accept(CreateResponseRequest(request_id='request-'+suffix, thread_id=thread,
                user_message_id=message.id, response_slot_id='slot-'+suffix,
                request_scope_hash=build_request_scope_hash(**scope, user_message_id=message.id),
                idempotency_key='lifecycle-idempotency-'+suffix, generation_id='generation-'+suffix,
                attempt_number=1, selected_model='fixture-model', deadline_at=datetime.now(UTC)+timedelta(minutes=3)))
        db.commit()


def _race(engine, *, same_request=False, canonical=False):
    barrier = Barrier(2)
    attempts = [0, 0]
    def acquire(index):
        with Session(engine) as db:
            repository = SqlAlchemyResponseLifecycleRepository(db)
            uow = SqlAlchemyResponseWorkflowUnitOfWork(db)
            # The fallback is intentional: the pre-fix reproduction shows that
            # unrelated request rows abort one another under the old policy.
            run = uow.run_database_unit if canonical else getattr(uow, 'run_lifecycle_unit', uow.run_database_unit)
            request = 'request-one' if same_request or index == 0 else 'request-two'
            def operation():
                attempts[index] += 1
                # Reproduce a legitimate small-table sequential plan. These
                # controls are test-only; production planner settings stay intact.
                db.execute(text('SET LOCAL enable_indexscan=off'))
                db.execute(text('SET LOCAL enable_bitmapscan=off'))
                repository.get_request(request)
                if attempts[index] == 1:
                    barrier.wait(timeout=5)
                now = datetime.now(UTC)
                return repository.acquire_lease(request_id=request, lease_token='lease-'+str(index),
                    now=now, lease_expires_at=now+timedelta(minutes=2))
            try:
                return run(operation).state.value
            except GenerationContractError as error:
                return str(error)
    with ThreadPoolExecutor(2) as executor:
        outcomes = list(executor.map(acquire, range(2)))
    return outcomes, attempts


@pytest.mark.parametrize('canonical', [True, False])
def test_independent_request_progress_avoids_cross_request_serialization(store, canonical):
    engine, _, _ = store
    _requests(engine)
    outcomes, attempts = _race(engine, canonical=canonical)
    assert outcomes == ['lease_acquired', 'lease_acquired']
    if canonical:
        assert max(attempts) > 1  # Control: the prior broad policy really aborts.
    else:
        assert attempts == [1, 1]
    with engine.connect() as db:
        assert db.scalar(text('SHOW transaction_isolation')) == 'serializable'
        assert db.scalar(text('SHOW transaction_read_only')) == 'off'
    assert engine.pool.checkedout() == 0


def test_same_request_still_has_one_lease_winner(store):
    engine, _, _ = store
    _requests(engine)
    outcomes, attempts = _race(engine, same_request=True)
    assert sorted(outcomes) == ['lease_acquired', 'response_lease_acquire_conflict']
    assert max(attempts) > 1  # Same-row conflict re-reads and keeps the CAS fence.
    with Session(engine) as db:
        row = SqlAlchemyResponseLifecycleRepository(db).get_request('request-one')
        assert row.lease_generation == 1
    assert engine.pool.checkedout() == 0
