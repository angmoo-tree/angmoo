import asyncio
from time import monotonic, sleep
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.runtime.memory.canonical_worker import CanonicalReadWorker, DeadlineSessionFactory


class NativeReader:
    def __init__(self, sessions): self.sessions = sessions
    def revalidate(self, _, mode):
        with self.sessions() as db:
            if mode == "long":
                return db.scalar(text("WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT sum(x) FROM n"))
            if mode == "locked": return db.scalar(text("SELECT count(*) FROM sample"))
            if mode == "wait": sleep(.2)
            return db.scalar(text("SELECT 1"))
    hydrate = revalidate


@pytest.fixture
def worker(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'canonical.sqlite'}", pool_size=1, max_overflow=0, pool_timeout=.05)
    sessions = DeadlineSessionFactory(sessionmaker(engine))
    work = CanonicalReadWorker(sessions, NativeReader(sessions))
    yield work, engine
    engine.dispose()


def test_deadline_native_interruption_heartbeat_cleanup_and_reuse(worker):
    work, engine = worker
    async def run():
        ticks = 0
        async def heartbeat():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(.005)
        pulse = asyncio.create_task(heartbeat())
        start = monotonic()
        with pytest.raises(TimeoutError):
            await work.revalidate_async(None, "long", deadline=start+.1)
        await work.queue.drain()
        assert monotonic()-start < 1 and ticks >= 5
        assert engine.pool.checkedout() == 0
        assert await work.revalidate_async(None, "short", deadline=monotonic()+1) == 1
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)
        await work.stop()
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
    asyncio.run(run())


def test_caller_cancellation_keeps_running_future_owned_until_drain(worker):
    work, engine = worker
    async def run():
        task = asyncio.create_task(work.revalidate_async(None, "long", deadline=monotonic()+5))
        await asyncio.sleep(.04)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        await work.stop()
        assert engine.pool.checkedout() == 0
    asyncio.run(run())


def test_capacity_queued_work_has_no_session_and_stop_closes_admission(worker):
    work, engine = worker
    async def run():
        tasks = [asyncio.create_task(work.revalidate_async(None, "wait", deadline=monotonic()+4)) for _ in range(8)]
        await asyncio.sleep(.04)
        assert engine.pool.checkedout() == 1
        with pytest.raises(RuntimeError, match="canonical_read_unavailable"):
            await work.revalidate_async(None, "short", deadline=monotonic()+1)
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await work.stop()
        assert engine.pool.checkedout() == 0
        with pytest.raises(RuntimeError, match="canonical_worker_closed"):
            await work.revalidate_async(None, "short", deadline=monotonic()+1)
    asyncio.run(run())


def test_exclusive_lock_obeys_remaining_budget_and_reuses_connection(worker):
    work, engine = worker
    with engine.connect() as setup:
        setup.exec_driver_sql("CREATE TABLE sample (id INTEGER)")
        setup.commit()
    import sqlite3
    locked = sqlite3.connect(engine.url.database)
    locked.execute("BEGIN EXCLUSIVE")
    async def run():
        start = monotonic()
        with pytest.raises(Exception):
            await work.revalidate_async(None, "locked", deadline=start+.1)
        await work.queue.drain()
        assert monotonic()-start < .5 and engine.pool.checkedout() == 0
        locked.rollback()
        assert await work.hydrate_async(None, "short", deadline=monotonic()+1) == 1
        await work.stop()
    try: asyncio.run(run())
    finally: locked.close()


def test_three_sns_recall_pairs_and_chat_share_one_worker_without_blocking_light_reads(tmp_path):
    from threading import get_ident
    from sqlalchemy import event
    engine = create_engine(f"sqlite:///{tmp_path / 'bundle.sqlite'}", pool_size=2, max_overflow=0, pool_timeout=.05)
    factory = sessionmaker(engine)
    sessions = DeadlineSessionFactory(factory)
    work = CanonicalReadWorker(sessions, NativeReader(sessions))
    worker_threads = set()
    event.listen(engine, "before_cursor_execute", lambda *_: worker_threads.add(get_ident()))
    async def run():
        deadline = monotonic() + 3
        ticks = 0
        async def pulse():
            nonlocal ticks
            while True:
                with factory() as light:
                    assert light.scalar(text("SELECT 1")) == 1
                ticks += 1
                await asyncio.sleep(.01)
        heartbeat = asyncio.create_task(pulse())
        tasks = [asyncio.create_task(work.revalidate_async(None, "wait", deadline=deadline)) for _ in range(7)]
        try:
            assert await asyncio.gather(*tasks) == [1] * 7
            assert ticks >= 30
            assert len(worker_threads - {get_ident()}) == 1
            assert engine.pool.checkedout() == 0
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            await work.stop()
    try: asyncio.run(run())
    finally: engine.dispose()
