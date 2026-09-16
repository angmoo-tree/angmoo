"""One opt-in worker: durable admission, daily/exit triggers and v2 selection."""

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












class MemoryBatchRuntime:
    def __init__(self, session_factory, provider_factory, *, generation_policy="legacy", episode_provider_factory=None, episode_prior_search=None) -> None:
        # Preserve safe success/attempt measurements without enabling verbose
        # SDK logging or changing application-wide log levels.
        logging.getLogger("app.domains.memory.service.batch_selection").setLevel(logging.INFO)
        logging.getLogger("app.domains.memory.service.episode_selection").setLevel(logging.INFO)
        logging.getLogger("app.runtime.memory.episode_batch").setLevel(logging.INFO)
        self.session_factory, self.provider_factory = session_factory, provider_factory
        if generation_policy not in {"legacy", "episode_v1"}:
            raise ValueError("memory_generation_policy_invalid")
        self.generation_policy = generation_policy
        self.episode_provider_factory = episode_provider_factory
        self.episode_prior_search = episode_prior_search
        self.preparation = build_preparation_dependencies(generation_policy=generation_policy)
        self.stop_event = asyncio.Event()
        self.lock = asyncio.Lock()
        self.task = None

    async def start(self) -> None:
        if self.task is not None and not self.task.done():
            return
        install_memory_delivery(self.session_factory)
        self.stop_event.clear()
        self.task = asyncio.create_task(self._loop(), name="memory-batch-worker")

    async def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                logger.warning("memory_batch_runtime_deferred")
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=5)
            except TimeoutError:
                pass

    def prepare(self, *, shutdown: bool = False) -> None:
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
            if not shutdown and self.generation_policy == "episode_v1":
                with self.session_factory() as db:
                    if chat_is_active(db, now=datetime.now(UTC)):
                        return "memory_foreground_deferred"
            self.prepare(shutdown=shutdown)
            with self.session_factory() as db:
                repository = SqlAlchemyMemoryBatchRepository(db)
                token = uuid4().hex
                batch = repository.claim(lease_token=token, now=datetime.now(UTC))
                repository.commit()
                if batch is None:
                    return "memory_batch_queue_empty"
                if batch.policy_version == "episode-selection.v1":
                    if self.episode_provider_factory is None:
                        repository.fail(batch, code="episode_provider_unconfigured", now=datetime.now(UTC))
                        repository.commit()
                        return "episode_provider_unconfigured"
                    from app.runtime.memory.episode_batch import run_episode_batch
                    return await run_episode_batch(repository, batch,
                        provider_factory=self.episode_provider_factory, timeout=timeout,
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

    async def pause(self) -> None:
        self.stop_event.set()
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def stop(self) -> None:
        await self.pause()
        uninstall_memory_delivery(self.session_factory)
