"""Real PG reads must not block ticks or leak a Session across worker boundaries."""
import asyncio
import contextvars
import threading

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from postgresql.test_activity_transactions import store
from app.runtime.resident.db_stage import run_slot_db_stage


def test_db_stage_returns_connection_and_propagates_context_without_blocking_loop(store):
    engine, _, _ = store
    fence = contextvars.ContextVar('test_fence')
    entered = threading.Event()
    release = threading.Event()
    async def scenario():
        original_thread = threading.get_ident()
        fence.set('epoch-7')
        with Session(engine) as source:
            source.scalar(select(1))
            def operation(db):
                assert db is not source and threading.get_ident() != original_thread
                assert db.get_bind() is engine and fence.get() == 'epoch-7'
                assert engine.pool.checkedout() == 0
                assert db.scalar(select(1)) == 1
                entered.set()
                assert release.wait(3)
                return {'ready': True}
            task = asyncio.create_task(run_slot_db_stage(source, operation))
            try:
                for _ in range(100):
                    if entered.is_set(): break
                    await asyncio.sleep(.01)
                assert entered.is_set() and not task.done()
            finally:
                release.set()
            assert await task == {'ready': True}
        assert engine.pool.checkedout() == 0
    asyncio.run(scenario())


def test_repeated_cancellation_drains_worker_before_parent_cleanup(store):
    engine, _, _ = store
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    async def scenario():
        with Session(engine) as source:
            def operation(db):
                db.scalar(select(1))
                entered.set()
                try:
                    assert release.wait(3)
                finally:
                    finished.set()
                return 1
            task = asyncio.create_task(run_slot_db_stage(source, operation))
            try:
                for _ in range(100):
                    if entered.is_set(): break
                    await asyncio.sleep(.01)
                assert entered.is_set()
                task.cancel()
                await asyncio.sleep(.02)
                task.cancel()
                await asyncio.sleep(.02)
                assert not task.done() and not finished.is_set()
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert finished.is_set()
        assert engine.pool.checkedout() == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('where', ['caller', 'worker'])
def test_pending_writes_cannot_be_discarded_or_cross_worker_boundary(store, where):
    from app.domains.identity.models import InstallationIdentity
    engine, _, _ = store
    def write(db):
        db.add(InstallationIdentity(singleton_key='local-installation',
            installation_id='pending-test', bootstrap_state='unclaimed'))
    async def scenario():
        with Session(engine) as source:
            if where == 'caller': write(source)
            def operation(db):
                if where == 'worker': write(db)
                return 1
            with pytest.raises(Exception, match='resident_stage_'):
                await run_slot_db_stage(source, operation)
            if where == 'caller': assert source.new
        with Session(engine) as check:
            assert check.get(InstallationIdentity, 'local-installation') is None
    asyncio.run(scenario())


def test_tick_dispatches_preparation_and_status_reads_off_loop_with_shared_engine(store, monkeypatch):
    from app.runtime.resident import execution
    from app.domains.routines.schemas import ResidentSlotTickCreate
    engine, _, _ = store
    original_thread = threading.get_ident()
    seen = []
    def prepare(db, data):
        assert threading.get_ident() != original_thread
        assert db.scalar(select(1)) == 1
        return 0, []
    def slots(db):
        assert threading.get_ident() != original_thread
        assert db.get_bind() is engine
        seen.append(db.scalar(select(1)))
        return []
    monkeypatch.setattr(execution, '_prepare_resident_tick', prepare)
    monkeypatch.setattr(execution, 'list_resident_slots', slots)
    async def scenario():
        with Session(engine) as source:
            result = await execution.tick_resident_slots(source, ResidentSlotTickCreate(max_runs=1))
            assert threading.get_ident() == original_thread
            assert result.started_count == result.due_count == 0
    asyncio.run(scenario())
    assert seen == [1] and engine.pool.checkedout() == 0


def test_empty_real_postgresql_tick_closes_preparation_transactions(store):
    from app.runtime.resident.execution import tick_resident_slots
    from app.domains.routines.schemas import ResidentSlotTickCreate
    engine, _, _ = store
    async def scenario():
        with Session(engine) as source:
            result = await tick_resident_slots(source, ResidentSlotTickCreate(max_runs=1))
            assert result.started_count == result.due_count == 0
    asyncio.run(scenario())
    assert engine.pool.checkedout() == 0
