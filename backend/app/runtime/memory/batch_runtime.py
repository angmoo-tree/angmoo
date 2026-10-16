"""One opt-in worker: durable admission, daily/exit triggers and v2 selection."""
from app.core import work_observation as observation

import asyncio
from app.domains.memory.service.batch_preparation import deliver_candidates, rebuild_briefs
from app.domains.memory.service.batch_scheduling import schedule_batches
from app.domains.memory.service.reconciliation import reconcile_sources
from app.runtime.memory.batch_preparation import build_preparation_dependencies
from collections import defaultdict
from datetime import UTC, date, datetime
import logging
from uuid import uuid4

from sqlalchemy import exists, func, insert, or_, select, update

from app.models import Base
from app.domains.memory.repository.delivery import sync_epoch
from app.domains.memory.policies.batch import (
    MAX_SELECTION_CANDIDATES,
    MEMORY_PROVIDER_TIMEOUT_SECONDS,
    MAX_SELECTION_INPUT_UTF8_BYTES,
    next_daily_slot,
    schedule_timezone,
)
from app.domains.memory.policies.consolidation import (
    deterministic_hot_brief,
    MEMORY_HOT_BRIEF_CONTRACT_VERSION,
)
from app.domains.memory.contracts.items import as_utc
from app.domains.memory.contracts.provenance import MemoryKindV1, MemorySourceTypeV1
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryDomainError
from app.domains.memory.service.batch_selection import MemoryBatchSelectionService
from app.domains.memory.service.items import (
    MemoryWriteLifecycleService,
    memory_evidence_blocked_code,
)
from app.domains.memory.models.batch import (
    MemoryActivationEpoch,
    MemoryBatchSetting,
    MemorySourceDelivery,
)
from app.runtime.memory.composition import (
    memory_batch_repository as SqlAlchemyMemoryBatchRepository,
)
from app.runtime.memory.composition import (
    memory_consolidation_repository as SqlAlchemyMemoryConsolidationRepository,
)
from app.runtime.memory.composition import (
    memory_repository as SqlAlchemyMemoryRepository,
)
from app.domains.memory.models.items import (
    MemoryCandidate,
    MemoryScopeSettingModel,
)
from app.runtime.memory.source_delivery import (
    install_memory_delivery,
    uninstall_memory_delivery,
)
from app.runtime.memory.source_composition import source_evidence_reader as SqlAlchemyMemorySourceEvidenceReader


logger = logging.getLogger(__name__)
SITUATION_RECEIPTS_PER_TURN = 32












class MemoryBatchRuntime:
    def __init__(self, session_factory, provider_factory, *, generation_policy="legacy", episode_provider_factory=None, activity_provider_factory=None, episode_prior_search=None, idle_work=None, data_root=None) -> None:
        # Preserve safe success/attempt measurements without enabling verbose
        # SDK logging or changing application-wide log levels.
        logging.getLogger("app.domains.memory.service.batch_selection").setLevel(logging.INFO)
        logging.getLogger("app.domains.memory.service.episode_selection").setLevel(logging.INFO)
        logging.getLogger("app.runtime.memory.episode_batch").setLevel(logging.INFO)
        self.session_factory, self.provider_factory = session_factory, provider_factory
        if generation_policy not in {"legacy", "episode_v1", "activity32", "activity_situation"}:
            raise ValueError("memory_generation_policy_invalid")
        self.generation_policy = generation_policy
        from app.runtime.memory.situation_runtime import SituationRuntime
        self.situations = SituationRuntime(session_factory, data_root=data_root) if generation_policy == "activity_situation" else None
        self.episode_provider_factory = episode_provider_factory
        self.activity_provider_factory = activity_provider_factory
        self.episode_prior_search = episode_prior_search
        self.idle_work = idle_work
        self.preparation = build_preparation_dependencies(generation_policy=generation_policy)
        self.stop_event = asyncio.Event()
        self.lock = asyncio.Lock()
        self.task = None
        from app.runtime.memory.canonical_work import MemoryCanonicalWork
        self._canonical = MemoryCanonicalWork() if self.situations is not None else None
        self._brief_cursor = ""

    async def start(self) -> None:
        if self.task is not None and not self.task.done():
            return
        if self.situations is None:
            install_memory_delivery(self.session_factory)
        self.stop_event.clear()
        if self._canonical is not None and self._canonical.closed:
            from app.runtime.memory.canonical_work import MemoryCanonicalWork
            self._canonical = MemoryCanonicalWork()
        self.task = asyncio.create_task(self._loop(), name="memory-batch-worker")

    async def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                logger.warning("memory_batch_runtime_deferred")
            observation.emit("wait", boundary="idle", operation="memory_batch_loop", reason="bounded_idle", planned_wait_ms=5000)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=5)
            except TimeoutError:
                pass

    def prepare(self, *, shutdown: bool = False) -> None:
        if self.situations is not None:
            self.situations.prepare(shutdown=shutdown)
            return
        with self.session_factory() as db:
            now = datetime.now(UTC)
            reconcile_sources(db, now=now, dependencies=self.preparation)
            deliver_candidates(db, dependencies=self.preparation)
            schedule_batches(db, now=now, shutdown=shutdown, dependencies=self.preparation)
        try:
            with self.session_factory() as db:
                rebuild_briefs(db, now=datetime.now(UTC), dependencies=self.preparation)
        except Exception:
            logger.warning("memory_batch_brief_rebuild_deferred")

    async def tick(self, *, shutdown: bool = False, timeout: float = MEMORY_PROVIDER_TIMEOUT_SECONDS) -> str:
        async with self.lock:
            from app.runtime.memory.foreground_priority import chat_is_active
            if self.situations is not None:
                applied = False
                for _ in range(SITUATION_RECEIPTS_PER_TURN):
                    # Each call still prepares/commits exactly one receipt and
                    # releases its Session/lease before the next submission.
                    result = await self._canonical.call(self._situation_tick, shutdown=shutdown)
                    if result != "situation_page_applied":
                        break
                    applied = True
                closing = shutdown or self.situations.quit_identity is not None
                if not closing and result != "memory_foreground_deferred":
                    await self._canonical.call(self._rebuild_situation_brief)
                if applied and result == "memory_batch_queue_empty":
                    return "situation_page_applied"
                if result == "memory_batch_queue_empty" and self.idle_work is not None and not closing:
                    return await self.idle_work()
                return result
            if not shutdown and self.generation_policy in {"episode_v1", "activity32"}:
                with self.session_factory() as db:
                    if chat_is_active(db, now=datetime.now(UTC)):
                        from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest
                        db.execute(update(MemoryConsolidationRequest).where(
                            MemoryConsolidationRequest.state.in_(("preparing", "queued"))).values(last_code="memory_foreground_deferred"))
                        db.commit()
                        observation.emit("wait", boundary="deferred", reason="foreground_chat")
                        return "memory_foreground_deferred"
            self.prepare(shutdown=shutdown)
            with self.session_factory() as db:
                repository = SqlAlchemyMemoryBatchRepository(db)
                token = uuid4().hex
                batch = repository.claim(lease_token=token, now=datetime.now(UTC))
                repository.commit()
                if batch is None:
                    if self.idle_work is not None and not shutdown:
                        return await self.idle_work()
                    return "memory_batch_queue_empty"
                if batch.policy_version in {"episode-selection.v1", "episode-activity-batch32.v1"}:
                    factory = self.activity_provider_factory if batch.credential_id is not None else self.episode_provider_factory
                    if factory is None:
                        repository.fail(batch, code="episode_provider_unconfigured", now=datetime.now(UTC))
                        repository.commit()
                        return "episode_provider_unconfigured"
                    from app.runtime.memory.episode_batch import run_episode_batch
                    return await run_episode_batch(repository, batch,
                        provider_factory=factory, timeout=timeout,
                        foreground_active=None if shutdown else chat_is_active, prior_search=self.episode_prior_search)
                reader = SqlAlchemyMemorySourceEvidenceReader(db)
                service = MemoryBatchSelectionService(
                    repository=repository,
                    source_reader=reader,
                    write_lifecycle=MemoryWriteLifecycleService(
                        repository.memory, reader
                    ),
                    provider_factory=self.provider_factory,
                )
                result = await service.run_next(
                    lease_token=token, timeout=timeout, claimed_batch=batch
                )
            return result

    @observation.observed("situation_tick")
    def _situation_tick(self, *, shutdown):
        from app.runtime.memory.foreground_priority import chat_is_active
        closing = shutdown or self.situations.quit_identity is not None
        if not closing:
            with self.session_factory() as db:
                if chat_is_active(db, now=datetime.now(UTC)):
                    observation.emit("wait", boundary="deferred", reason="foreground_chat")
                    return "memory_foreground_deferred"
        self.situations.prepare(shutdown=closing)
        return self.situations.tick()

    def _rebuild_situation_brief(self):
        from app.domains.memory.models.activity_situation import MemorySituationProcessingSetting
        with self.session_factory() as db:
            # Rebuild once after the bounded application burst, rather than
            # inserting a slow brief read between every two batch candidates.
            self._brief_cursor = rebuild_briefs(db, now=datetime.now(UTC), dependencies=self.preparation,
                settings_type=MemorySituationProcessingSetting, limit=1, after=self._brief_cursor)

    async def prepare_async(self, *, shutdown=False):
        if self._canonical is not None:
            await self._canonical.call(self.prepare, shutdown=shutdown)
        else:
            self.prepare(shutdown=shutdown)

    async def run_canonical(self, function, *args):
        if self._canonical is not None:
            return await self._canonical.call(function, *args)
        return function(*args)

    async def fence_async(self):
        if self.situations is not None:
            return await self._canonical.call(self.situations.fence)
        return False

    async def pause(self) -> None:
        self.stop_event.set()
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self._canonical is not None:
            await self._canonical.drain()

    async def stop(self) -> None:
        await self.pause()
        if self._canonical is not None:
            self._canonical.close()
        uninstall_memory_delivery(self.session_factory)
