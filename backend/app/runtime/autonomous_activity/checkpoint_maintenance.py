"""Bounded, per-root checkpoint maintenance independent of SNS scheduling."""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from pathlib import Path
import time

from sqlalchemy import select

from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.routines.models import AgentPublicActionExecution, AgentRun, AgentSlot
from app.domains.routines.models.plans import ActivityBeat, ActivityEventConsumption
from app.domains.social.models.posts import Post, PostImageGenerationJob
from app.domains.social.models.manual_writes import OwnerManualInboxCandidate
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.contracts.checkpoint_retention import completion, utc
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service import checkpoint_retention as policy
from app.runtime.autonomous_activity.checkpoints import activity_checkpointer
from app.runtime.migrations.generation import EmbeddedGenerationError, EmbeddedUpgradeLock

logger = logging.getLogger(__name__)


def validate_completion_receipts(db, row) -> None:
    """Cross-domain receipt checks use the same canonical read transaction."""
    value = completion(row)
    actor = db.get(WorldCharacter, row.world_character_id)
    if actor is None or actor.world_id != row.world_id:
        raise ValueError("activity_completed_receipts_invalid")
    receipts = db.scalars(select(AgentPublicActionExecution).where(
        AgentPublicActionExecution.run_id == row.activity_id)).all()
    succeeded = 0
    for receipt in receipts:
        if (receipt.character_id != actor.character_id
                or receipt.world_id not in (None, row.world_id)
                or receipt.actor_world_character_id not in (None, actor.id)):
            raise ValueError("activity_completed_receipts_invalid")
        if receipt.status == "succeeded":
            if receipt.completed_at is None or not isinstance(receipt.result, dict):
                raise ValueError("activity_completed_receipts_invalid")
            succeeded += 1
    # A resumed child can report a previously applied effect as "reused" and
    # therefore have fewer newly applied effects than its durable receipts.
    if succeeded < value.publish_result.public_action_count:
        raise ValueError("activity_completed_receipts_invalid")


def protection_reason(db, row, *, now) -> str | None:
    """Protect actual recovery owners, not only a matching activity ID."""
    actor = db.get(WorldCharacter, row.world_character_id)
    if actor is None:
        return "actor_missing"
    live = db.scalar(select(AgentSlot.agent_id).join(
        AgentRun, AgentRun.id == AgentSlot.locked_by_run_id).where(
        AgentSlot.assigned_character_id == actor.character_id,
        AgentRun.character_id == actor.character_id,
        AgentRun.status == "running", AgentSlot.lease_expires_at > utc(now)).limit(1))
    if live is not None:
        return "live_actor_lease"
    if db.scalar(select(AgentPublicActionExecution.id).where(
        AgentPublicActionExecution.run_id == row.activity_id,
        AgentPublicActionExecution.status == "pending").limit(1)) is not None:
        return "pending_public_effect"
    for model in (ActivityBeat, ActivityEventConsumption, OwnerManualInboxCandidate):
        if db.scalar(select(model.id).where(model.claim_run_id == row.activity_id,
                model.status == "claimed").limit(1)) is not None:
            return "pending_activity_claim"
    reservations = (row.result or {}).get("recovery_reservations", [])
    if not isinstance(reservations, list) or any(not isinstance(item, str) for item in reservations):
        # These are spent call keys, not pending jobs. The completed graph
        # confirms delivery; unknown future contracts remain protected.
        return "recovery_reservation_unconfirmed"
    receipts = db.scalars(select(AgentPublicActionExecution).where(
        AgentPublicActionExecution.run_id == row.activity_id,
        AgentPublicActionExecution.scope == "writing",
        AgentPublicActionExecution.status == "succeeded")).all()
    for receipt in receipts:
        post_id = (receipt.result or {}).get("post_id")
        if not post_id:
            return "published_post_unconfirmed"
        post = db.get(Post, post_id)
        if post is None:
            return "published_post_missing"
        if db.scalar(select(PostImageGenerationJob.id).where(
                PostImageGenerationJob.post_id == post_id,
                PostImageGenerationJob.status.not_in(("succeeded", "failed", "skipped", "cancelled"))).limit(1)) is not None:
            return "image_recovery_pending"
    try:
        validate_completion_receipts(db, row)
    except ValueError:
        return "completion_receipts_invalid"
    return None


@dataclass(frozen=True)
class MaintenanceLimits:
    interval_seconds: float = 3600
    batch_size: int = 50
    maximum_candidates: int = 500
    start_budget_seconds: float = 5
    sqlite_busy_ms: int = 50

    def __post_init__(self):
        if min(self.interval_seconds, self.batch_size, self.maximum_candidates,
               self.start_budget_seconds, self.sqlite_busy_ms) <= 0:
            raise ValueError("checkpoint_maintenance_limits_invalid")


async def _finish_io(awaitable):
    """Cancellation waits for active I/O before closing its connection/lock."""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class CheckpointMaintenance:
    def __init__(self, *, data_root: Path, session_factory, enabled: bool = True,
                 clock=lambda: datetime.now(UTC), limits: MaintenanceLimits | None = None,
                 monotonic_clock=time.monotonic):
        self.data_root = data_root.resolve()
        self.session_factory = session_factory
        self.enabled, self.clock = enabled, clock
        self.monotonic = monotonic_clock
        self.limits = limits or MaintenanceLimits()
        self._stop = asyncio.Event()
        self._task = None
        self._cursor = None
        self.last_cycle: dict = {}

    async def start(self):
        if not self.enabled or self._task is not None:
            return
        self._stop.clear()
        await self.cycle()
        self._task = asyncio.create_task(self._periodic(), name="sns-checkpoint-maintenance")

    async def stop(self):
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _periodic(self):
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.limits.interval_seconds)
            except TimeoutError:
                await self.cycle()

    def _read_candidates(self, now):
        with self.session_factory() as db:
            driver = db.connection().connection.driver_connection
            previous = driver.execute("PRAGMA busy_timeout").fetchone()[0]
            driver.execute(f"PRAGMA busy_timeout={self.limits.sqlite_busy_ms}")
            try:
                return policy.candidates(db, now=now, cursor=self._cursor, limit=self.limits.batch_size)
            finally:
                driver.execute(f"PRAGMA busy_timeout={previous}")

    def _claim(self, identifier, now):
        with self.session_factory() as db:
            def operation():
                row = db.get(ActivityGraphRun, identifier)
                if row is None or not policy.eligible(row, now=now):
                    return None, "ineligible"
                reason = protection_reason(db, row, now=now)
                if reason:
                    return None, reason
                token = policy.claim(db, row, now=now)
                return token, "claimed" if token else "changed"
            return run_sqlite_session_immediate(db, operation, require_clean=True)

    def _mark(self, identifier, token):
        with self.session_factory() as db:
            def operation():
                row = db.get(ActivityGraphRun, identifier)
                return row is not None and policy.mark_pruned(db, row, token=token)
            return run_sqlite_session_immediate(db, operation, require_clean=True)

    async def cycle(self):
        counts = Counter()
        started = self.monotonic()
        delete_times = []
        lock = EmbeddedUpgradeLock(self.data_root / "runtime" / "activity" / "checkpoint-maintenance.lock")
        if not self.enabled:
            return {"disabled": 1}
        try:
            lock.__enter__()
        except (EmbeddedGenerationError, OSError):
            return {"locked": 1}
        try:
            async with activity_checkpointer(self.data_root, busy_ms=self.limits.sqlite_busy_ms) as saver:
                while not self._stop.is_set() and sum(counts.values()) < self.limits.maximum_candidates:
                    now = self.clock()
                    rows = await _finish_io(asyncio.to_thread(self._read_candidates, now))
                    if not rows:
                        self._cursor = None
                        break
                    for finished, identifier in rows:
                        if (self._stop.is_set() or sum(counts.values()) >= self.limits.maximum_candidates
                                or self.monotonic() - started >= self.limits.start_budget_seconds):
                            break
                        self._cursor = (finished, identifier)
                        try:
                            token, reason = await _finish_io(asyncio.to_thread(self._claim, identifier, now))
                            if token is None:
                                counts[reason] += 1
                            else:
                                deleting = self.monotonic()
                                await _finish_io(saver.adelete_thread(f"activity:{identifier}"))
                                delete_times.append(self.monotonic() - deleting)
                                marked = await _finish_io(asyncio.to_thread(self._mark, identifier, token))
                                counts["pruned" if marked else "mark_changed"] += 1
                        except Exception as exc:
                            # Release an SDK transaction if a delete failed
                            # before its own commit; don't hold its writer lock
                            # while examining another candidate.
                            await _finish_io(saver.conn.rollback())
                            counts["deferred"] += 1
                            logger.warning("checkpoint_cleanup_deferred type=%s", type(exc).__name__)
                        await asyncio.sleep(0)
                    if self.monotonic() - started >= self.limits.start_budget_seconds:
                        break
        except Exception as exc:
            counts["cycle_deferred"] += 1
            logger.warning("checkpoint_maintenance_deferred type=%s", type(exc).__name__)
        finally:
            lock.__exit__(None, None, None)
        self.last_cycle = {**dict(counts), "duration_ms": round((self.monotonic() - started) * 1000, 3),
            "max_delete_ms": round(max(delete_times, default=0) * 1000, 3)}
        return self.last_cycle
