"""Cancellation drains a real SQLite Session without starving the async loop."""
import asyncio
from threading import Event, get_ident

import pytest
from sqlalchemy import text

from memory.test_p8_l_h_canonical_recall import runtime_factory
from app.runtime.memory.canonical_work import MemoryCanonicalWork

pytestmark = pytest.mark.usefixtures("deny_external_network")


def test_cancelled_sql_operation_remains_owned_serialized_and_drained(runtime_factory):
    worker = MemoryCanonicalWork()
    entered, release, second_entered = Event(), Event(), Event()
    main_thread = get_ident()
    def slow_read():
        assert get_ident() != main_thread
        with runtime_factory() as db:
            assert db.scalar(text("SELECT 1")) == 1
            entered.set()
            assert release.wait(5)
            assert db.scalar(text("SELECT 2")) == 2
    def next_read():
        second_entered.set()
        with runtime_factory() as db:
            return db.scalar(text("SELECT 3"))
    async def exercise():
        first = asyncio.create_task(worker.call(slow_read))
        for _ in range(100):
            if entered.is_set(): break
            await asyncio.sleep(0.01)
        assert entered.is_set()  # The loop kept serving timers during SQL work.
        first.cancel()
        with pytest.raises(asyncio.CancelledError): await first
        second = asyncio.create_task(worker.call(next_read))
        drained = asyncio.create_task(worker.drain())
        try:
            await asyncio.sleep(0.05)
            assert not second_entered.is_set() and not drained.done()
        finally:
            release.set()
        assert await asyncio.wait_for(second, 2) == 3
        await asyncio.wait_for(drained, 2)
        worker.close()
        with pytest.raises(RuntimeError, match="worker_closed"):
            await worker.call(next_read)
    try:
        asyncio.run(exercise())
    finally:
        release.set()
        worker.close()
