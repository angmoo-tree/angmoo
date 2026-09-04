"""Authenticated host shutdown preparation; child windows never call this."""

import asyncio
from datetime import UTC, datetime
import time

from sqlalchemy import select
from starlette.responses import JSONResponse

from app.domains.memory.infrastructure.batch_models import MemoryBatchRun
from app.domains.memory.infrastructure.sqlalchemy_models import MemoryMaintenanceJob


class MemoryShutdownCoordinator:
    def __init__(self, memory, *, budget_seconds=30, quiesce=None):
        self.memory = memory
        self.budget_seconds = budget_seconds
        self.quiesce = quiesce
        self.phase = "RUNNING"
        self.deferred = False
        self.started_at = None
        self.task = None
        self.requests = set()
        self.stop_requested = asyncio.Event()

    @property
    def closing(self):
        return self.phase != "RUNNING"

    def status(self):
        return {"phase": self.phase, "deferred": self.deferred}

    def start(self):
        if self.task is None:
            self.phase, self.started_at = "QUIESCING", time.monotonic()
            self.task = asyncio.create_task(
                self._prepare(), name="memory-shutdown-prepare"
            )
        return self.status()

    def skip(self):
        self.stop_requested.set()
        self.deferred = True
        return self.status()

    async def _bounded(self, coroutine, timeout):
        task = asyncio.create_task(coroutine)
        skip_task = asyncio.create_task(self.stop_requested.wait())
        try:
            done, _ = await asyncio.wait(
                {task, skip_task},
                timeout=max(0, timeout),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if skip_task in done:
                raise asyncio.CancelledError
            if task in done:
                return task.result()
            raise TimeoutError
        finally:
            skip_task.cancel()
            if not task.done():
                task.cancel()
                task.add_done_callback(_consume)

    async def _prepare(self):
        deadline = self.started_at + self.budget_seconds
        try:
            await self._bounded(self.memory.pause(), min(2, self.budget_seconds))
            for task in tuple(self.requests):
                task.cancel()
            if self.quiesce is not None:
                await self._bounded(
                    self.quiesce(), min(5, max(0, deadline - time.monotonic() - 5))
                )
            self.phase = "PREPARING"
            self.memory.prepare(shutdown=True)
            self.phase = "CONSOLIDATING"
            for _ in range(8):
                remaining = (
                    deadline - time.monotonic() - min(5, self.budget_seconds / 4)
                )
                if remaining <= 0 or self.stop_requested.is_set():
                    self.deferred = True
                    break
                result = await self._bounded(
                    self.memory.tick(timeout=remaining), remaining
                )
                if result == "memory_batch_queue_empty":
                    break
            else:
                # The bounded drain is not a claim that all work completed.
                self.deferred = True
        except (Exception, asyncio.CancelledError):
            self.deferred = True
        finally:
            self.phase = "FINALIZING"
            # Fence even providers which ignore cancellation. Their old lease
            # can never commit after the host abandons the attempt.
            try:
                with self.memory.session_factory() as db:
                    now = datetime.now(UTC)
                    jobs = db.scalars(
                        select(MemoryMaintenanceJob)
                        .join(
                            MemoryBatchRun,
                            MemoryBatchRun.job_id == MemoryMaintenanceJob.id,
                        )
                        .where(MemoryMaintenanceJob.status == "running")
                    ).all()
                    for job in jobs:
                        job.status = "pending" if job.attempt_count < 3 else "failed"
                        job.started_at = (
                            None if job.status == "pending" else job.started_at
                        )
                        job.completed_at = now if job.status == "failed" else None
                        job.lease_token = job.lease_expires_at = None
                        job.last_error_code = "memory_selection_interrupted"
                        self.deferred = True
                    db.commit()
            except Exception:
                # A damaged/busy DB must not strand the native host in closing.
                # Persisted leases still expire; the host's hard bound remains.
                self.deferred = True
            try:
                # This records pending cutoffs even on immediate exit. No AI.
                self.memory.prepare(shutdown=True)
            except Exception:
                self.deferred = True
            self.phase = "EXIT_READY"


def _consume(task):
    if not task.cancelled():
        task.exception()


class MemoryShutdownAdmissionMiddleware:
    def __init__(self, app, *, coordinator):
        self.app, self.coordinator = app, coordinator

    async def __call__(self, scope, receive, send):
        mutation = (
            scope["type"] == "http"
            and scope["method"] not in {"GET", "HEAD", "OPTIONS"}
            and not scope["path"].startswith("/__angmoo/desktop/")
        )
        if mutation and self.coordinator.closing:
            await JSONResponse(
                {"detail": "local_runtime_shutting_down"}, status_code=503
            )(scope, receive, send)
            return
        task = asyncio.current_task()
        if mutation:
            self.coordinator.requests.add(task)
        try:
            await self.app(scope, receive, send)
        finally:
            self.coordinator.requests.discard(task)
