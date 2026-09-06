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
    def __init__(self, session_factory, provider_factory) -> None:
        self.session_factory, self.provider_factory = session_factory, provider_factory
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
            reconcile_sources(db, now=now, dependencies=build_preparation_dependencies())
            deliver_candidates(db, dependencies=build_preparation_dependencies())
            schedule_batches(db, now=now, shutdown=shutdown, dependencies=build_preparation_dependencies())
        try:
            with self.session_factory() as db:
                rebuild_briefs(db, now=datetime.now(UTC), dependencies=build_preparation_dependencies())
        except Exception:
            logger.warning("memory_batch_brief_rebuild_deferred")

    async def tick(self, *, shutdown: bool = False, timeout: float = 30) -> str:
        async with self.lock:
            self.prepare(shutdown=shutdown)
            with self.session_factory() as db:
                repository = SqlAlchemyMemoryBatchRepository(db)
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
                    lease_token=uuid4().hex, timeout=timeout
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
