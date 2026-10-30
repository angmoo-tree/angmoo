"""Final evidence guards keep a bounded independent PostgreSQL read lane."""
import asyncio
from threading import Event
from time import monotonic
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from postgresql.test_canonical_contracts import engine
from app.runtime.memory.canonical_worker import CanonicalReadWorker, DeadlineSessionFactory


def test_guard_can_read_while_bulk_recall_is_busy_and_stop_drains_both(engine):
    sessions = DeadlineSessionFactory(sessionmaker(engine))
    entered, release = Event(), Event()
    class Reader:
        def resolve(self, _, rows):
            with sessions() as db:
                db.scalar(text('SELECT 1'))
                entered.set()
                assert release.wait(5)
                return 1
        def assert_current(self, _, rows):
            with sessions() as db:
                return db.scalar(text('SELECT 2'))
    worker = CanonicalReadWorker(sessions, Reader(), separate_guard=True)
    async def scenario():
        task=asyncio.create_task(worker.resolve_async(None, (), deadline=monotonic()+5))
        try:
            for _ in range(200):
                if entered.is_set():break
                await asyncio.sleep(.005)
            assert entered.is_set()
            assert await worker.assert_current_async(None, (), deadline=monotonic()+1)==2
            assert not task.done() and engine.pool.checkedout()==1
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        finally:
            release.set()
            await worker.stop()
        assert engine.pool.checkedout()==0
        with pytest.raises(RuntimeError, match='canonical_worker_closed'):
            await worker.assert_current_async(None, (), deadline=monotonic()+1)
    asyncio.run(scenario())


def test_guard_deadline_still_interrupts_native_sql_and_returns_connection(engine):
    sessions=DeadlineSessionFactory(sessionmaker(engine))
    class Reader:
        def assert_current(self, _, rows):
            with sessions() as db:
                return db.execute(text('SELECT pg_sleep(3)')).all()
    worker=CanonicalReadWorker(sessions, Reader(), separate_guard=True)
    async def scenario():
        start=monotonic()
        with pytest.raises(TimeoutError):
            await worker.assert_current_async(None, (), deadline=start+.1)
        await worker.stop()
        assert monotonic()-start<1.5 and engine.pool.checkedout()==0
        with engine.connect() as db:assert db.scalar(text('SELECT 1'))==1
    asyncio.run(scenario())
