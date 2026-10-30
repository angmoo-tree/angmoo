"""Lease writes share the real PostgreSQL deadline and confirmed-abort policy."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from postgresql.test_activity_transactions import store
from app.core.postgresql_concurrency import PostgresDeadlineExceeded
from app.core.sqlite_concurrency import SqliteRetryPolicy
from app.domains.identity.models import InstallationIdentity
from app.domains.runtime.contracts.lease import SchedulerTickResult
from app.runtime.persistence.lease_operation import LeaseOperation, lease_operation_scope
from app.runtime.persistence.scheduler_lease import SqlAlchemySchedulerLeaseRepository


def repository(engine):
    with Session(engine) as db:
        db.add(InstallationIdentity(singleton_key='local-installation',
            installation_id='scheduler-pg-test', bootstrap_state='unclaimed'))
        db.commit()
    return SqlAlchemySchedulerLeaseRepository(sessionmaker(engine))


def test_lease_retries_confirmed_abort_and_never_checks_out_after_commit(store):
    engine, _, _ = store
    repo = repository(engine)
    first = repo.acquire(owner_id='owner', ttl_seconds=45)
    attempts = []; checkouts = []
    def inject(connection, cursor, statement, parameters, context, many):
        if statement.startswith('UPDATE runtime_scheduler_leases'):
            attempts.append(statement)
            if len(attempts) == 1:
                connection.exec_driver_sql("DO $$ BEGIN RAISE EXCEPTION 'synthetic' USING ERRCODE='40001'; END $$")
    def checkout(*args): checkouts.append(1)
    event.listen(engine, 'before_cursor_execute', inject)
    event.listen(engine, 'checkout', checkout)
    try:
        proof = repo.heartbeat(owner_id='owner', fencing_epoch=first.fencing_epoch, ttl_seconds=45)
        assert proof.lease_owner_id == 'owner'
        assert len(attempts) == len(checkouts) == 2  # One checkout per transaction attempt.
    finally:
        event.remove(engine, 'before_cursor_execute', inject)
        event.remove(engine, 'checkout', checkout)
    permit = repo.begin_tick(owner_id='owner', fencing_epoch=first.fencing_epoch, ttl_seconds=45, interval_seconds=60)
    assert permit.should_run
    result = repo.finish_tick(owner_id='owner', fencing_epoch=first.fencing_epoch,
        expected_tick=permit.logical_window_at, finished_at=datetime.now(UTC), result=SchedulerTickResult.SUCCESS)
    assert result.last_tick_result is SchedulerTickResult.SUCCESS
    assert repo.release(owner_id='owner', fencing_epoch=first.fencing_epoch).lease_owner_id is None


def test_lease_pool_wait_is_bounded_and_does_not_replay_a_tick(store):
    engine, _, _ = store
    repo = repository(engine)
    first = repo.acquire(owner_id='owner', ttl_seconds=45)
    held = [engine.connect() for _ in range(4)]
    try:
        with ThreadPoolExecutor(max_workers=1) as worker:
            future = worker.submit(repo.heartbeat, owner_id='owner', fencing_epoch=first.fencing_epoch, ttl_seconds=45)
            time.sleep(.35)  # Longer than one pool checkout timeout, within the lease budget.
            held.pop().close()
            assert future.result(timeout=3).lease_owner_id == 'owner'
        assert repo.read().last_tick_window_at is None
    finally:
        for connection in held: connection.close()


def test_lease_expired_operation_rolls_back_before_publication(store):
    engine, _, _ = store
    repo = repository(engine)
    first = repo.acquire(owner_id='owner', ttl_seconds=45)
    def slow_read(connection, cursor, statement, parameters, context, many):
        if statement.startswith('SELECT runtime_scheduler_leases.'):
            time.sleep(.08)
    event.listen(engine, 'before_cursor_execute', slow_read)
    try:
        with lease_operation_scope(LeaseOperation('deadline', time.monotonic()+.05,
                SqliteRetryPolicy(max_attempts=1, maximum_elapsed_seconds=.05))):
            with pytest.raises(PostgresDeadlineExceeded):
                repo.heartbeat(owner_id='owner', fencing_epoch=first.fencing_epoch, ttl_seconds=45)
    finally:
        event.remove(engine, 'before_cursor_execute', slow_read)
    assert repo.read().heartbeat_at == first.heartbeat_at


def test_child_activity_uses_supplied_runtime_pool_and_closes_session(store, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.database import create_session_factory
    from app.runtime.resident import execution
    from sqlalchemy import text
    engine, _, _ = store
    seen = []
    monkeypatch.setattr(execution.slot_queries, 'get_agent_slot', lambda db, agent_id: SimpleNamespace(agent_id=agent_id))
    async def execute(db, **kwargs):
        assert db.get_bind() is engine
        assert db.scalar(text('SELECT 1')) == 1
        seen.append(db)
        await asyncio.sleep(.01)
        return kwargs['slot'].agent_id
    monkeypatch.setattr(execution, '_run_resident_slot_once', execute)
    factory = create_session_factory(engine)
    async def scenario():
        return await asyncio.gather(*(execution._run_claimed_resident_slot_once(str(i),
            session_factory=factory, post_id=None, timeout_seconds=5, message=None) for i in range(2)))
    assert asyncio.run(scenario()) == ['0', '1']
    assert len(seen) == 2 and seen[0] is not seen[1]
    assert engine.pool.checkedout() == 0


def test_same_owner_reacquires_expired_postgres_lease_with_new_fence(store):
    from app.domains.runtime.exceptions import SchedulerLeaseLostError
    engine, _, _ = store
    repo = repository(engine)
    first = repo.acquire(owner_id='same-process', ttl_seconds=30)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE runtime_scheduler_leases SET lease_expires_at = clock_timestamp() - interval '1 second'")
    restored = repo.acquire(owner_id='same-process', ttl_seconds=30)
    assert restored.fencing_epoch == first.fencing_epoch + 1
    with pytest.raises(SchedulerLeaseLostError):
        repo.heartbeat(owner_id='same-process', fencing_epoch=first.fencing_epoch, ttl_seconds=30)
    assert repo.heartbeat(owner_id='same-process', fencing_epoch=restored.fencing_epoch, ttl_seconds=30)
