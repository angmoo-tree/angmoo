"""Owned, bounded SQL work; cancellation never abandons an open Session."""
import asyncio
from threading import Lock

from app.core.sqlite_concurrency import SqliteBoundedTaskQueue


def _consume(waiter):
    if not waiter.cancelled():
        waiter.exception()


class MemoryCanonicalWork:
    def __init__(self):
        self._queue = SqliteBoundedTaskQueue(max_workers=1, capacity=2)
        self._lock = Lock()
        self._futures = set()
        self.closed = False

    async def call(self, operation, *args, **kwargs):
        if self.closed:
            raise RuntimeError("memory_canonical_worker_closed")
        # The operation opens/closes its own Session in this worker. Neither a
        # request's Session nor an ORM entity is transported to another thread.
        future = self._queue.submit(operation, *args, **kwargs)
        with self._lock:
            self._futures.add(future)
        def complete(done):
            with self._lock:
                self._futures.discard(done)
            if not done.cancelled():
                done.exception()
        future.add_done_callback(complete)
        waiter = asyncio.wrap_future(future)
        waiter.add_done_callback(_consume)
        try:
            return await asyncio.shield(waiter)
        except asyncio.CancelledError:
            future.cancel()  # Queued work cancels; running work remains owned.
            raise

    async def drain(self):
        with self._lock:
            pending = tuple(self._futures)
        waiters = [asyncio.wrap_future(future) for future in pending]
        for waiter in waiters:
            waiter.add_done_callback(_consume)
        if waiters:
            await asyncio.wait(waiters)

    def close(self):
        self.closed = True
        self._queue.close(wait=False)
