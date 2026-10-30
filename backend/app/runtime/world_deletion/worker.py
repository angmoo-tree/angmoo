"""One durable deletion owner; bounded DB retries never replay external effects."""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, delete

from app.core.sqlite_concurrency import SqliteAsyncTaskQueue, is_sqlite_contention
from app.core.database_transactions import database_write
from app.domains.worlds.models_deletion import WorldDeletionRequest, WorldDeletionCleanupItem
from app.runtime.world_deletion.cleanup_effects import ErasureLeaseLost, clean_step, require_lease

log = logging.getLogger(__name__)


class WorldDeletionWorker:
    def __init__(self, session_factory, ports, *, batch_size=100):
        self.sessions, self.ports, self.batch_size = session_factory, ports, batch_size
        self.task = None
        self.stopping = asyncio.Event()
        self._work = SqliteAsyncTaskQueue(capacity=1)
        self._fenced_results = set()
        self._queue_wakeup = None

    async def start(self):
        if self.task is not None and not self.task.done():
            return
        if self._work.closed:
            self._work = SqliteAsyncTaskQueue(capacity=1)
        self.stopping.clear()
        from app.core.committed_queue_wakeup import CommittedQueueWakeup
        self._queue_wakeup = CommittedQueueWakeup(self.sessions, {WorldDeletionRequest.__tablename__})
        self.task = asyncio.create_task(self._run(), name="world-deletion")

    async def stop(self):
        self.stopping.set()
        if self._queue_wakeup:
            self._queue_wakeup.close()
        try:
            if self.task:
                await asyncio.shield(self.task)
        finally:
            await self._work.drain()
            self._work.close()
            self.task = None

    async def _run(self):
        while not self.stopping.is_set():
            self._queue_wakeup.begin_poll()
            failed = False
            try:
                worked = await self._work.call(self.tick)
            except Exception as exc:
                log.error("world_deletion_worker_tick_failed error_type=%s", type(exc).__name__)
                worked, failed = False, True
            timeout = 0.05 if worked else (1 if failed or not self._queue_wakeup.enabled else 5)
            if not self.stopping.is_set():
                if worked:
                    try:
                        await asyncio.wait_for(self.stopping.wait(), timeout)
                    except TimeoutError:
                        pass
                else:
                    await self._queue_wakeup.wait(timeout)

    def tick(self):
        try:
            claim = self._claim()
        except Exception as exc:
            if is_sqlite_contention(exc):
                return False
            raise
        if claim is None:
            return False
        request_id, epoch, stage = claim
        try:
            if request_id not in self._fenced_results:
                with self.sessions() as db:
                    world_id = require_lease(db, request_id, epoch).world_id
                self.ports.close_result_admission(world_id)
                self._fenced_results.add(request_id)
            cleaned = clean_step(self.sessions, self.ports, request_id, epoch) if stage == "cleaning" else None
            with self.sessions() as db:
                database_write(db,
                    lambda: self._advance(db, request_id, epoch, cleaned), require_clean=True)
        except ErasureLeaseLost:
            return False
        except Exception as exc:
            busy = is_sqlite_contention(exc)
            try:
                self._record_failure(request_id, epoch, exc, busy=busy)
            except ErasureLeaseLost:
                return False
            except Exception as recording_error:
                if not is_sqlite_contention(recording_error):
                    raise
                # Keep durable stage/cursor/items and recover via lease expiry.
            log.warning("world_deletion_deferred stage=%s code=%s error_type=%s request_id=%s",
                stage, "storage_busy" if busy else "cleanup_failed", type(exc).__name__, request_id)
            return False
        return True

    def _claim(self):
        def due(now):
            return (WorldDeletionRequest.state.not_in(("failed", "completed")),
                or_(WorldDeletionRequest.lease_until.is_(None), WorldDeletionRequest.lease_until < now),
                or_(WorldDeletionRequest.next_attempt_at.is_(None), WorldDeletionRequest.next_attempt_at <= now))
        # Empty queues need one read, not a configured writer transaction every
        # second. A fresh write below rechecks all lease/due conditions.
        with self.sessions() as db:
            if db.get_bind().dialect.name == 'postgresql':
                if db.scalar(select(WorldDeletionRequest.id).where(*due(datetime.now(UTC))).limit(1)) is None:
                    return None
        with self.sessions() as db:
            def claim():
                now = datetime.now(UTC)
                row = db.scalar(select(WorldDeletionRequest).where(*due(now))
                    .order_by(WorldDeletionRequest.updated_at, WorldDeletionRequest.accepted_at).limit(1))
                if row is None:
                    return None
                row.lease_epoch += 1
                row.lease_until = now + timedelta(seconds=30)
                return row.id, row.lease_epoch, row.stage
            return database_write(db, claim, require_clean=True)

    def _advance(self, db, request_id, epoch, cleaned):
        row = require_lease(db, request_id, epoch)
        now, stage = datetime.now(UTC), row.stage
        row.state = "draining" if stage == "collecting" else stage
        if stage == "cleaning":
            done = cleaned
        elif stage == "draining":
            done = self.ports.drain(db, row.world_id)
            accepted = row.accepted_at.replace(tzinfo=UTC) if row.accepted_at.tzinfo is None else row.accepted_at
            if not done and now - accepted > timedelta(minutes=5):
                raise ValueError("world_erasure_effect_unsettled")
        elif stage == "collecting":
            done = self.ports.collect(db, row, self.batch_size)
        elif stage == "purging":
            done = self.ports.purge(db, row, self.batch_size)
        elif stage == "verifying":
            done = self.ports.verify(db, row)
        else:
            raise ValueError("world_erasure_stage_invalid")
        if done:
            stages = ("draining", "collecting", "purging", "cleaning", "verifying", "completed")
            row.stage = stages[stages.index(stage) + 1]
            row.cursor = 0
            row.state = "draining" if row.stage == "collecting" else row.stage
            if row.state == "completed":
                row.completed_at = now
                db.execute(delete(WorldDeletionCleanupItem).where(WorldDeletionCleanupItem.request_id == row.id))
        row.lease_until = None
        row.failure_code = None
        row.next_attempt_at = now + timedelta(seconds=1) if not done and stage == "draining" else None
        row.updated_at = now

    def _record_failure(self, request_id, epoch, exc, *, busy):
        with self.sessions() as db:
            def record():
                row = require_lease(db, request_id, epoch)
                now = datetime.now(UTC)
                row.lease_until = None
                if busy:
                    row.state, row.failure_code = "retry_wait", "storage_busy"
                    row.next_attempt_at = now + timedelta(seconds=1)
                else:
                    row.failures += 1
                    # Invalid preservation material will not heal by repeating
                    # the same query. Retain the journal for explicit user retry.
                    contract_error = isinstance(exc, ValueError) and str(exc) != "world_erasure_effect_unsettled"
                    row.state = "failed" if contract_error or row.failures >= 3 else "retry_wait"
                    row.failure_code = "cleanup_failed"
                    row.next_attempt_at = now + timedelta(seconds=(2, 5, 15)[min(row.failures - 1, 2)])
                row.updated_at = now
            database_write(db, record, require_clean=True)
