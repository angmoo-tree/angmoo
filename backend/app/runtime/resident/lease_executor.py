"""Small lease operations only; retain real executor futures through cancellation."""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future
from threading import Lock
from time import monotonic
from typing import Any, Callable

from app.core.sqlite_concurrency import SqliteBoundedTaskQueue
from app.exceptions import SqliteTaskQueueFull

logger = logging.getLogger(__name__)


class SchedulerLeaseExecutor:
    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._coordinator: Any = None
        self._queue = SqliteBoundedTaskQueue(max_workers=1, capacity=4)
        self._futures: set[Future] = set()
        self._lock = Lock()
        self._closed = False

    async def call(self, operation: str, **kwargs: Any) -> Any:
        if self._closed:
            raise RuntimeError("scheduler_lease_executor_closed")
        submitted = monotonic()

        def execute() -> Any:
            delay = monotonic() - submitted
            if delay > 1:
                raise SqliteTaskQueueFull("scheduler_lease_queue_deadline")
            logger.info("scheduler_lease_queue operation=%s queue_ms=%.3f owner=%s epoch=%s",
                        operation, delay * 1000, kwargs.get("owner_id"), kwargs.get("fencing_epoch"))
            # The injected session/bind is first resolved inside the worker.
            if self._coordinator is None:
                self._coordinator = self._factory()
            return getattr(self._coordinator, operation)(**kwargs)

        future = self._queue.submit(execute)
        with self._lock:
            self._futures.add(future)

        def complete(done: Future) -> None:
            with self._lock:
                self._futures.discard(done)
            # Retrieve the exception even if the async waiter was cancelled.
            if not done.cancelled():
                error = done.exception()
                if error is not None:
                    logger.warning("scheduler_lease_operation_failed operation=%s code=%s", operation, type(error).__name__)

        future.add_done_callback(complete)
        waiter = asyncio.wrap_future(future)
        waiter.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            return await asyncio.shield(waiter)
        except asyncio.CancelledError:
            future.cancel()  # A queued call cancels; a running call remains tracked.
            raise

    async def drain(self, timeout: float) -> bool:
        with self._lock:
            pending = tuple(self._futures)
        for future in pending:
            future.cancel()
        if not pending:
            return True
        waiters = [asyncio.wrap_future(future) for future in pending]
        for waiter in waiters:
            waiter.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        _, unfinished = await asyncio.wait(waiters, timeout=max(0.01, timeout))
        for waiter in waiters:
            if waiter.done() and not waiter.cancelled():
                waiter.exception()
        return not unfinished

    def close(self) -> None:
        self._closed = True
        self._queue.close(wait=False)


async def lease_call(coordinator: Any, operation: str, **kwargs: Any) -> Any:
    if isinstance(coordinator, SchedulerLeaseExecutor):
        return await coordinator.call(operation, **kwargs)
    # Compatibility for direct private-helper tests. Product runners always
    # receive the executor above and never run a lease operation on the loop.
    return getattr(coordinator, operation)(**kwargs)
