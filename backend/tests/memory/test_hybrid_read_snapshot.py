"""A canonical resolve shares a WAL snapshot but never reserves the writer."""
import asyncio
from threading import Event
from time import monotonic
from sqlalchemy import create_engine, text, update
from sqlalchemy.orm import sessionmaker
from app.runtime.memory.canonical_worker import CanonicalReadWorker, DeadlineSessionFactory
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.domains.memory.models.items import MemoryScopeSettingModel
from memory.recall_cost_fixture import build_cost_case


async def wait_entered(event):
    async with asyncio.timeout(5):
        while not event.is_set():
            await asyncio.sleep(.005)


def test_resolve_pins_snapshot_and_next_guard_sees_permission_change(tmp_path):
    engine, reader, request, candidates = build_cost_case(tmp_path / "snapshot.sqlite", count=2)
    sessions = DeadlineSessionFactory(sessionmaker(engine))
    entered, release = Event(), Event()
    class PausedDetails(RuntimeEpisodeDetailReader):
        def prepare_situation_sources(self, contexts, *, validation):
            super().prepare_situation_sources(contexts, validation=validation)
            entered.set()
            assert release.wait(5)
    reader.factory, reader.details = sessions, PausedDetails
    worker = CanonicalReadWorker(sessions, reader)
    async def run():
        task = asyncio.create_task(worker.resolve_async(request, candidates, deadline=monotonic()+8))
        try:
            await wait_entered(entered)
            # Commit on an independent connection while expensive validation waits.
            # The MemoryItem versions and every source remain unchanged.
            with engine.begin() as writer:
                writer.execute(update(MemoryScopeSettingModel).values(enabled=False))
            release.set()
            result = await task
            assert result.validated_count == 2 and len(result.hydration.records) == 2
            reader.details = RuntimeEpisodeDetailReader
            fresh = await worker.resolve_async(request, candidates, deadline=monotonic()+5)
            assert fresh.validated_count == 0 and fresh.hydration.records == ()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            await worker.stop()
    try: asyncio.run(run())
    finally: engine.dispose()


def test_expensive_read_does_not_block_independent_write_or_async_timers(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'writer.sqlite'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql("CREATE TABLE state (value INTEGER)")
        connection.exec_driver_sql("INSERT INTO state VALUES (1)")
    sessions = DeadlineSessionFactory(sessionmaker(engine))
    entered, release = Event(), Event()
    class Reader:
        def resolve(self, *_):
            with sessions() as db:
                first = db.scalar(text("SELECT value FROM state"))
                entered.set()
                assert release.wait(5)
                return first, db.scalar(text("SELECT value FROM state"))
    worker = CanonicalReadWorker(sessions, Reader())
    async def run():
        task = asyncio.create_task(worker.resolve_async(None, (), deadline=monotonic()+8))
        try:
            await wait_entered(entered)
            with engine.begin() as writer:
                writer.exec_driver_sql("UPDATE state SET value=2")
            await asyncio.sleep(.02)
            assert not task.done()
            release.set()
            assert await task == (1, 1)
            assert await worker.resolve_async(None, (), deadline=monotonic()+2) == (2, 2)
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            await worker.stop()
    try: asyncio.run(run())
    finally: engine.dispose()
