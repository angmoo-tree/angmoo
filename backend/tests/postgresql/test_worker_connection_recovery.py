"""Outages resume durable owners, never replay unknown transactions or effects."""
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import psycopg
import pytest
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.core.postgresql_concurrency import (
    PostgresCommitOutcomeUnknown, connection_unavailable, retryable, transact,
)
from app.core.sqlite_concurrency import SqliteRetryPolicy
from app.runtime.graph_projection.worker import GraphProjectionWorker, ProjectionBatchResult
from app.runtime.resident import scheduler
from postgresql.test_activity_transactions import store


def disconnected():
    return OperationalError(None, None, psycopg.errors.AdminShutdown('synthetic outage'),
                            connection_invalidated=True)


@pytest.mark.parametrize('original,expected', [
    (psycopg.errors.AdminShutdown('test'), True),
    (psycopg.errors.CrashShutdown('test'), True),
    (psycopg.errors.CannotConnectNow('test'), True),
    (psycopg.OperationalError('test'), True),
    (psycopg.errors.InvalidPassword('test'), False),
    (psycopg.errors.InsufficientPrivilege('test'), False),
    (psycopg.errors.UndefinedTable('test'), False),
    (psycopg.errors.UniqueViolation('test'), False),
])
def test_outage_classification_is_separate_from_transaction_replay(original, expected):
    failure = OperationalError(None, None, original)
    assert connection_unavailable(failure) is expected
    assert not retryable(failure)


@pytest.mark.parametrize('stage', ['claim', 'load_command', 'finalize_success', 'unknown_ack'])
def test_projector_retains_claim_and_recovers_without_spending_failure_attempt(stage):
    class Outbox:
        calls = 0
        def claim(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                if stage == 'claim': raise disconnected()
                return (SimpleNamespace(id='owned', projection_type='test'),)
            return ()  # A durable receipt/claim is reconciled by the next poll.
        def load_command(self, **kwargs):
            if stage == 'load_command': raise disconnected()
            return 'versioned-command'
        def finalize_success(self, **kwargs):
            if stage == 'unknown_ack': raise PostgresCommitOutcomeUnknown('test')
            raise disconnected()
        def finalize_failure(self, **kwargs):
            pytest.fail('DB outage must not consume a graph failure attempt')
        def has_unfinished(self): return False
    class Stop:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, delay): delays.append(delay)
    stop, states, delays, applied = Stop(), [], [], []
    def observe(state):
        states.append(state)
        if state == 'ready': stop.stopped = True
    graph = SimpleNamespace(apply=lambda *args, **kwargs: applied.append(args) or 'applied')
    worker = GraphProjectionWorker(outbox=Outbox(), store=graph, worker_id='owned')
    worker.run_loop(stop_event=stop, connectivity_probe=lambda: None, state_listener=observe)
    assert states == ['degraded', 'ready']
    assert len(applied) == int(stage in ('finalize_success', 'unknown_ack'))
    assert delays[0] == 2


@pytest.mark.parametrize('stage', ['acquire', 'begin', 'finish', 'unknown_finish', 'heartbeat'])
def test_scheduler_reacquires_durable_window_without_duplicate_effect(tmp_path, monkeypatch, stage):
    calls, states, effects = [], [], []
    consumed = False
    failed = False
    config = Settings().model_copy(update={
        'RESIDENT_TICK_READY_PATH': str(tmp_path/'ready'),
        'RESIDENT_TICK_PROCESS_LOCK_PATH': str(tmp_path/'lock'),
    })
    def proof(owner):
        return SimpleNamespace(lease_owner_id=owner, fencing_epoch=1,
            lease_expires_at=datetime.now(UTC)+timedelta(seconds=60))
    def inject(where):
        nonlocal failed
        if not failed and stage == where:
            failed = True
            if where == 'unknown_finish': raise PostgresCommitOutcomeUnknown('test')
            raise disconnected()
    class Coordinator:
        def acquire(self, **kw):
            calls.append('acquire'); inject('acquire'); return proof(kw['owner_id'])
        def heartbeat(self, **kw):
            calls.append('heartbeat'); inject('heartbeat'); return proof(kw['owner_id'])
        def begin_tick(self, **kw):
            nonlocal consumed
            calls.append('begin'); inject('begin')
            run = not consumed; consumed = True
            return SimpleNamespace(should_run=run, logical_window_at=datetime.now(UTC))
        def finish_tick(self, **kw):
            calls.append('finish'); inject('finish'); inject('unknown_finish')
            return proof(kw['owner_id'])
        def release(self, **kw): calls.append('release')
    async def scenario():
        stop = asyncio.Event()
        async def tick():
            effects.append('one'); return SimpleNamespace(started_count=1)
        async def idle(**kwargs): stop.set(); return False
        monkeypatch.setattr(scheduler, '_sleep_until_next_tick_with_heartbeat', idle)
        await asyncio.wait_for(scheduler.run_resident_tick_scheduler(
            coordinator=Coordinator(), config=config, stop_event=stop,
            tick_runner=tick, state_listener=states.append), 5)
    asyncio.run(scenario())
    assert failed and effects == ['one'] and calls.count('acquire') == 2
    assert 'degraded' in states and states[-1] == 'stopped'
    assert calls.count('finish') == 1 and not scheduler.scheduler_is_ready(config)


def test_unsettled_scheduler_child_prevents_outage_restart(tmp_path, monkeypatch):
    calls, states = [], []
    config = Settings().model_copy(update={'RESIDENT_TICK_READY_PATH': str(tmp_path/'ready'),
        'RESIDENT_TICK_PROCESS_LOCK_PATH': str(tmp_path/'lock')})
    lease = SimpleNamespace(fencing_epoch=1, lease_expires_at=datetime.now(UTC)+timedelta(seconds=30))
    class Coordinator:
        def acquire(self, **kw): calls.append('acquire'); lease.lease_owner_id=kw['owner_id']; return lease
        def heartbeat(self, **kw): return lease
        def begin_tick(self, **kw): calls.append('begin'); return SimpleNamespace(should_run=True)
        def release(self, **kw): calls.append('release')
    async def scenario():
        release=asyncio.Event(); child=asyncio.create_task(release.wait())
        primary=disconnected(); primary.pending_tasks=(child,)
        async def fail(**kw): raise primary
        monkeypatch.setattr(scheduler, '_run_fenced_tick_with_heartbeat', fail)
        with pytest.raises(OperationalError):
            await scheduler.run_resident_tick_scheduler(coordinator=Coordinator(),config=config,
                state_listener=states.append,drain_timeout_seconds=.01)
        assert calls == ['acquire','begin'] and states[-1]=='failed'
        release.set(); await child
    asyncio.run(scenario())


def test_real_connection_termination_is_not_replayed_and_pool_reconnects(store):
    engine, _, _ = store
    attempts=[]
    def operation(connection):
        attempts.append(1)
        pid=connection.exec_driver_sql('SELECT pg_backend_pid()').scalar_one()
        with engine.connect() as admin:
            assert admin.exec_driver_sql('SELECT pg_terminate_backend(%s)', (pid,)).scalar_one()
        return connection.exec_driver_sql('SELECT 1').scalar_one()
    with pytest.raises(OperationalError) as failure:
        transact(engine, operation, retry_policy=SqliteRetryPolicy(max_attempts=4, maximum_elapsed_seconds=2))
    assert connection_unavailable(failure.value) and attempts == [1]
    with engine.connect() as connection: assert connection.exec_driver_sql('SELECT 1').scalar_one()==1
