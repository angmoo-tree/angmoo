"""Slow review storage must not starve scheduler/checkpoint async work."""
import asyncio
import threading
import time

import pytest
from sqlalchemy import event

from app.domains.relationships.service.daily_review import run_review_step
from app.runtime.memory.canonical_work import MemoryCanonicalWork
from app.runtime.relationships.review_runtime import RelationshipReviewRuntime
from relationships.test_review_received_recovery import setup
from test_relationship_daily_review import Provider, References


def test_runtime_keeps_all_storage_off_event_loop(tmp_path, monkeypatch):
    engine, sessions, world, identifier, journal = setup(tmp_path)
    worker = MemoryCanonicalWork()
    provider = Provider()
    runtime = RelationshipReviewRuntime(sessions, lambda base: provider, canonical_work=worker.call)
    runtime.journal = journal
    monkeypatch.setattr('app.runtime.relationships.review_runtime.ReviewMemoryReferences', lambda db: References())
    monkeypatch.setattr('app.runtime.relationships.manual_review_worker.advance_manual_requests', lambda *a, **k: None)
    monkeypatch.setattr('app.runtime.relationships.review_preparation.prepare_due_reviews', lambda *a: None)
    monkeypatch.setattr('app.runtime.relationships.review_transitions.transition', lambda *a, **k: 'prepared')
    event_thread = threading.get_ident()
    sql_threads = set()
    first_sql = threading.Event()

    def slow_storage(*args):
        sql_threads.add(threading.get_ident())
        if not first_sql.is_set():
            first_sql.set()
            time.sleep(.12)

    event.listen(engine, 'before_cursor_execute', slow_storage)

    async def exercise():
        task = asyncio.create_task(runtime.tick())
        try:
            while not first_sql.is_set():
                await asyncio.sleep(.001)
            await asyncio.sleep(.02)
            assert not task.done()  # Scheduler work still runs during slow SQL.
            assert await task == 'ready'
        finally:
            await worker.drain()

    try:
        asyncio.run(exercise())
        assert len(provider.calls) == 1
        assert sql_threads and event_thread not in sql_threads
    finally:
        event.remove(engine, 'before_cursor_execute', slow_storage)
        worker.close()
        engine.dispose()


def test_cancel_after_response_recovers_journal_without_second_provider(tmp_path):
    engine, sessions, world, identifier, journal = setup(tmp_path)
    worker, provider = MemoryCanonicalWork(), Provider()

    async def exercise():
        pending = asyncio.Event()

        async def cancel_boundary(function, *args):
            if function.__name__ == 'may_publish':
                assert journal.read(world, identifier)['result_digest']
                pending.set()
                await asyncio.Event().wait()
            return await worker.call(function, *args)

        task = asyncio.create_task(run_review_step(sessions, work_id=identifier,
            references_factory=lambda db: References(), provider_factory=lambda base: provider,
            journal=journal, received={}, database_work=cancel_boundary))
        try:
            await asyncio.wait_for(pending.wait(), 10)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await run_review_step(sessions, work_id=identifier,
                references_factory=lambda db: References(), provider_factory=lambda base: provider,
                journal=journal, received={}, database_work=worker.call) == 'ready'
            assert len(provider.calls) == 1
            assert journal.read(world, identifier) is None
        finally:
            task.cancel()
            await worker.drain()

    try:
        asyncio.run(exercise())
    finally:
        worker.close()
        engine.dispose()
