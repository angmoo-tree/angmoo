"""One bounded durable deletion worker, independent of autonomy scheduling."""
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from sqlalchemy import and_, or_, select, update, delete
from app.domains.worlds.models_deletion import WorldDeletionRequest, WorldDeletionCleanupItem

log = logging.getLogger(__name__)


class WorldDeletionWorker:
    def __init__(self, session_factory, ports, *, batch_size=100):
        self.sessions, self.ports, self.batch_size = session_factory, ports, batch_size
        self.task = None
        self.stopping = asyncio.Event()

    async def start(self):
        self.stopping.clear()
        self.task = asyncio.create_task(self._run(), name="world-deletion")

    async def stop(self):
        self.stopping.set()
        if self.task:
            await asyncio.wait_for(self.task, timeout=10)
            self.task = None

    async def _run(self):
        while not self.stopping.is_set():
            try:
                worked = await asyncio.to_thread(self.tick)
            except Exception:
                log.exception("world_deletion_worker_tick_failed")
                worked = False
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=0.05 if worked else 1)
            except TimeoutError:
                pass

    def tick(self):
        now = datetime.now(UTC)
        with self.sessions() as db:
            row = db.scalar(select(WorldDeletionRequest).where(
                WorldDeletionRequest.state.not_in(("failed", "completed")),
                or_(WorldDeletionRequest.lease_until.is_(None), WorldDeletionRequest.lease_until < now),
                or_(WorldDeletionRequest.next_attempt_at.is_(None), WorldDeletionRequest.next_attempt_at <= now))
                .order_by(WorldDeletionRequest.accepted_at).limit(1))
            if row is None:
                return False
            request_id, epoch = row.id, row.lease_epoch
            claimed = db.execute(update(WorldDeletionRequest).where(WorldDeletionRequest.id == request_id,
                WorldDeletionRequest.lease_epoch == epoch,
                or_(WorldDeletionRequest.lease_until.is_(None), WorldDeletionRequest.lease_until < now),
                WorldDeletionRequest.state.not_in(("completed", "failed"))).values(lease_epoch=epoch + 1,
                lease_until=now + timedelta(seconds=30))).rowcount
            db.commit()
            if not claimed:
                return False
        stage = "claim"
        try:
            with self.sessions() as db:
                row = db.get(WorldDeletionRequest, request_id)
                if row.lease_epoch != epoch + 1:
                    return False
                stage = row.stage
                row.state = stage if stage != "collecting" else "draining"
                done = False
                if stage == "draining":
                    done = self.ports.drain(db, row.world_id)
                    accepted = row.accepted_at.replace(tzinfo=UTC) if row.accepted_at.tzinfo is None else row.accepted_at
                    if not done and now - accepted > timedelta(minutes=5):
                        raise ValueError("world_erasure_effect_unsettled")
                elif stage == "collecting":
                    done = self.ports.collect(db, row, self.batch_size)
                elif stage == "purging":
                    done = self.ports.purge(db, row, self.batch_size)
                elif stage == "cleaning":
                    done = self.ports.clean(db, row, self.batch_size)
                elif stage == "verifying":
                    done = self.ports.verify(db, row)
                if done:
                    stages = ("draining", "collecting", "purging", "cleaning", "verifying", "completed")
                    row.stage = stages[stages.index(stage) + 1]
                    row.cursor = 0
                    row.state = "draining" if row.stage == "collecting" else row.stage
                    if row.state == "completed":
                        row.completed_at = now
                        # Completed receipts retain neither file paths nor row inventories.
                        db.execute(delete(WorldDeletionCleanupItem).where(WorldDeletionCleanupItem.request_id == row.id))
                row.lease_until = None
                row.failure_code = None
                row.next_attempt_at = now + timedelta(seconds=1) if not done and stage == "draining" else None
                row.updated_at = now
                db.commit()
        except Exception as exc:
            with self.sessions() as db:
                current = db.get(WorldDeletionRequest, request_id)
                if current is None or current.lease_epoch != epoch + 1:
                    return True  # The newer lease owns cursor/ack; no stale mutation.
                delay = (2, 5, 15)[min(current.failures, 2)]
                db.execute(update(WorldDeletionRequest).where(WorldDeletionRequest.id == request_id,
                    WorldDeletionRequest.lease_epoch == epoch + 1).values(
                    failures=WorldDeletionRequest.failures + 1, lease_until=None,
                    state="retry_wait", failure_code="cleanup_failed", next_attempt_at=now + timedelta(seconds=delay)))
                db.execute(update(WorldDeletionRequest).where(WorldDeletionRequest.id == request_id,
                    WorldDeletionRequest.lease_epoch == epoch + 1, WorldDeletionRequest.failures >= 3).values(state="failed"))
                db.commit()
            # Original configuration validation may contain user text. Keep
            # operational diagnostics to identity, stage and exception type.
            log.error("world_deletion_stage_failed stage=%s error_type=%s request_id=%s", stage, type(exc).__name__, request_id)
        return True
