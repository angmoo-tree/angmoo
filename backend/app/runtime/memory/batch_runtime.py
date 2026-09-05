"""One opt-in worker: durable admission, daily/exit triggers and v2 selection."""

import asyncio
from app.domains.memory.service.batch_preparation import deliver_candidates, rebuild_briefs
from app.domains.memory.service.batch_scheduling import schedule_batches
from app.runtime.memory.batch_preparation import build_preparation_dependencies
from collections import defaultdict
from datetime import UTC, date, datetime
import logging
from uuid import uuid4

from sqlalchemy import exists, func, insert, or_, select, update

from app.core.db import Base
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
from app.runtime.memory.sqlalchemy_source_reader import (
    SqlAlchemyMemorySourceEvidenceReader,
)


logger = logging.getLogger(__name__)


def reconcile_sources(session, *, now: datetime) -> None:
    """Per-source anti-join retains holes; persisted scan order rotates scopes.

    Only source timestamps inside a recorded ON epoch are recoverable. The
    transactional normal path uses commit-time admission, not display time.
    Upgrade opens an epoch now, never retroactively assumes old consent.
    """
    epochs = MemoryActivationEpoch.__table__
    missing_epoch = ~exists(
        select(epochs.c.id).where(
            epochs.c.scope_setting_id == MemoryScopeSettingModel.id,
            epochs.c.scope_version == MemoryScopeSettingModel.version,
        )
    )
    for setting in session.scalars(
        select(MemoryScopeSettingModel)
        .where(MemoryScopeSettingModel.enabled.is_(True), missing_epoch)
        .limit(32)
    ):
        sync_epoch(session.connection(), setting.id, now=now)
    scanned = session.scalars(
        select(MemoryActivationEpoch)
        .join(
            MemoryScopeSettingModel,
            MemoryScopeSettingModel.id == MemoryActivationEpoch.scope_setting_id,
        )
        .where(MemoryScopeSettingModel.enabled.is_(True))
        .order_by(
            MemoryActivationEpoch.last_scanned_at.asc().nullsfirst(),
            MemoryActivationEpoch.id,
        )
        .limit(16)
    ).all()
    tables = Base.metadata.tables
    for epoch in scanned:
        setting = session.get(MemoryScopeSettingModel, epoch.scope_setting_id)
        subject = setting.subject_world_character_id
        posts, likes, events = (
            tables["posts"],
            tables["post_likes"],
            tables["social_events"],
        )
        messages, threads, observations = (
            tables["message_messages"],
            tables["message_threads"],
            tables["world_character_feed_observations"],
        )
        catalogs = [
            (
                posts,
                posts.c.created_at,
                posts.c.id,
                ("POST", "REPLY"),
                [
                    posts.c.world_id == setting.world_id,
                    posts.c.author_world_character_id == subject,
                ],
                posts,
            ),
            (
                likes,
                likes.c.created_at,
                likes.c.id,
                ("REACTION",),
                [
                    likes.c.world_id == setting.world_id,
                    likes.c.actor_world_character_id == subject,
                ],
                likes,
            ),
            (
                events,
                events.c.created_at,
                events.c.id,
                ("SOCIAL_EVENT",),
                [
                    events.c.world_id == setting.world_id,
                    or_(
                        events.c.actor_world_character_id == subject,
                        events.c.target_world_character_id == subject,
                    ),
                    ~events.c.event_type.in_(
                        (
                            "post_published",
                            "reply_created",
                            "comment_created",
                            "like_added",
                        )
                    ),
                ],
                events,
            ),
            (
                messages.join(threads, threads.c.id == messages.c.thread_id),
                messages.c.created_at,
                messages.c.id,
                ("CHAT_MESSAGE",),
                [
                    threads.c.world_id == setting.world_id,
                    threads.c.responding_world_character_id == subject,
                    messages.c.role == "assistant",
                    messages.c.status == "ok",
                    threads.c.world_scope_status == "resolved",
                ],
                messages,
            ),
            (
                observations.join(posts, posts.c.id == observations.c.post_id),
                observations.c.observed_at,
                posts.c.id,
                ("POST", "REPLY"),
                [
                    observations.c.world_id == setting.world_id,
                    observations.c.observer_world_character_id == subject,
                    observations.c.status == "observed",
                ],
                posts,
            ),
        ]
        for source, captured, identity, kinds, predicates, content in catalogs:
            delivery = MemorySourceDelivery.__table__
            missing = ~exists(
                select(delivery.c.sequence).where(
                    delivery.c.scope_setting_id == setting.id,
                    delivery.c.source_type.in_(kinds),
                    delivery.c.source_id == identity.cast(delivery.c.source_id.type),
                )
            )
            predicates += [captured >= epoch.opened_at, missing]
            if epoch.closed_at is not None:
                predicates.append(captured < epoch.closed_at)
            rows = (
                session.execute(
                    select(content, captured.label("admitted_at"))
                    .select_from(source)
                    .where(*predicates)
                    .order_by(captured, identity)
                    .limit(32)
                )
                .mappings()
                .all()
            )
            for row in rows:
                kind = (
                    ("REPLY" if row["reply_to_post_id"] else "POST")
                    if kinds == ("POST", "REPLY")
                    else kinds[0]
                )
                # Invalid sources also receive terminal entries via revalidation.
                if (
                    session.scalar(
                        select(delivery.c.sequence).where(
                            delivery.c.scope_setting_id == setting.id,
                            delivery.c.source_type == kind,
                            delivery.c.source_id == str(row["id"]),
                        )
                    )
                    is None
                ):
                    session.execute(
                        insert(delivery).values(
                            scope_setting_id=setting.id,
                            epoch_id=epoch.id,
                            source_type=kind,
                            source_id=str(row["id"]),
                            state="pending",
                            captured_at=row["admitted_at"],
                        )
                    )
        epoch.last_scanned_at = now
    session.commit()










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
            reconcile_sources(db, now=now)
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
