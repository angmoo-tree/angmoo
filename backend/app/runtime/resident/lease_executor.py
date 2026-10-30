"""Small lease operations only; retain real executor futures through cancellation."""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future
from threading import Lock
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from app.core.sqlite_concurrency import SqliteBoundedTaskQueue, SqliteRetryPolicy
from app.exceptions import SqliteTaskQueueFull
from app.runtime.persistence.lease_operation import LeaseOperation, lease_operation_scope

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
        deadline = kwargs.pop("queue_deadline", None)
        deadline_timeout = kwargs.pop("deadline_timeout", None)
        caller = asyncio.current_task()
        cancellation_count = caller.cancelling() if caller else 0
        finished_at = [None]
        policy = None
        if deadline is not None and operation in {"heartbeat", "finish_tick"}:
            policy = SqliteRetryPolicy(max_attempts=12 if operation == "heartbeat" else 4,
                initial_delay_seconds=0.05, maximum_delay_seconds=0.2,
                maximum_elapsed_seconds=2.0)
        observation = LeaseOperation(uuid4().hex, deadline, policy)
        observation.record({"result": "queued", "worker_state": "queued"})

        def execute() -> Any:
            delay = monotonic() - submitted
            observation.record({"queue_ms": round(delay * 1000, 3), "worker_state": "running"})
            if delay > 1 or (deadline is not None and monotonic() >= deadline):
                raise SqliteTaskQueueFull("scheduler_lease_queue_deadline")
            logger.info("scheduler_lease_queue operation=%s operation_id=%s queue_ms=%.3f owner=%s epoch=%s",
                        operation, observation.operation_id, delay * 1000, kwargs.get("owner_id"), kwargs.get("fencing_epoch"))
            # The injected session/bind is first resolved inside the worker.
            with lease_operation_scope(observation):
                if self._coordinator is None:
                    self._coordinator = self._factory()
                try:
                    return getattr(self._coordinator, operation)(**kwargs)
                finally:
                    # Record on the worker, before Future completion. Event-loop
                    # delivery may be delayed even when the DB finished on time.
                    finished_at[0] = monotonic()

        future = self._queue.submit(execute)
        with self._lock:
            self._futures.add(future)

        def complete(done: Future) -> None:
            with self._lock:
                self._futures.discard(done)
            # Retrieve the exception even if the async waiter was cancelled.
            if not done.cancelled():
                error = done.exception()
                observation.record({"worker_state": "done", "total_ms": round((monotonic() - submitted) * 1000, 3)})
                facts = observation.snapshot()
                if error is not None or facts.get("caller_cancelled"):
                    event = "scheduler_lease_operation_failed" if error is not None else "scheduler_lease_operation_finished"
                    logger.warning("%s operation=%s code=%s facts=%s",
                                   event, operation, type(error).__name__ if error is not None else "late_success", facts)

        future.add_done_callback(complete)
        waiter = asyncio.wrap_future(future)
        waiter.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            return await asyncio.shield(waiter)
        except asyncio.CancelledError:
            if (operation == "heartbeat" and deadline_timeout is not None
                    and deadline_timeout.expired() and caller is not None
                    and caller.cancelling() == cancellation_count + 1
                    and deadline is not None and finished_at[0] is not None
                    and finished_at[0] <= deadline and future.done()
                    and not future.cancelled() and future.exception() is None):
                # Only this call's deadline cancellation can adopt an already
                # committed result. External cancellation and late/unknown writes
                # still drain/fence normally. The caller rechecks lease safety.
                logger.info("scheduler_heartbeat_delivery_delayed operation_id=%s completed_ms=%.3f delivery_ms=%.3f",
                    observation.operation_id, (finished_at[0] - submitted) * 1000,
                    (monotonic() - submitted) * 1000)
                return future.result()
            future.cancel()  # A queued call cancels; a running call remains tracked.
            observation.record({"caller_cancelled": True, "worker_state":
                "cancelled" if future.cancelled() else "running" if future.running() else "done"})
            logger.warning("scheduler_lease_wait_cancelled operation=%s facts=%s", operation, observation.snapshot())
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
    kwargs.pop("queue_deadline", None)
    kwargs.pop("deadline_timeout", None)
    return getattr(coordinator, operation)(**kwargs)
