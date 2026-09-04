"""One opt-in worker: durable admission, daily/exit triggers and v2 selection."""

import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime
import logging
from uuid import uuid4

from sqlalchemy import exists, func, insert, or_, select, update

from app.core.db import Base
from app.domains.memory.domain.batch_policy import (
    MAX_SELECTION_CANDIDATES,
    MAX_SELECTION_INPUT_UTF8_BYTES,
    next_daily_slot,
    schedule_timezone,
)
from app.domains.memory.domain.consolidation import (
    deterministic_hot_brief,
    MEMORY_HOT_BRIEF_CONTRACT_VERSION,
)
from app.domains.memory.domain.lifecycle import as_utc
from app.domains.memory.domain.provenance import MemoryKindV1, MemorySourceTypeV1
from app.domains.memory.domain.scope import MemoryScope
from app.domains.memory.domain.errors import MemoryDomainError
from app.domains.memory.application.batch_selection import MemoryBatchSelectionService
from app.domains.memory.application.write_lifecycle import (
    MemoryWriteLifecycleService,
    memory_evidence_blocked_code,
)
from app.domains.memory.infrastructure.batch_models import (
    MemoryActivationEpoch,
    MemoryBatchSetting,
    MemorySourceDelivery,
)
from app.domains.memory.infrastructure.batch_repository import (
    SqlAlchemyMemoryBatchRepository,
)
from app.domains.memory.infrastructure.consolidation_repository import (
    SqlAlchemyMemoryConsolidationRepository,
)
from app.domains.memory.infrastructure.repository import SqlAlchemyMemoryRepository
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MemoryCandidate,
    MemoryScopeSettingModel,
)
from app.runtime.memory.source_delivery import (
    install_memory_delivery,
    sync_epoch,
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


def deliver_candidates(session, *, limit: int = 128) -> int:
    rows = session.scalars(
        select(MemorySourceDelivery)
        .join(
            MemoryScopeSettingModel,
            MemoryScopeSettingModel.id == MemorySourceDelivery.scope_setting_id,
        )
        .where(
            MemorySourceDelivery.state == "pending",
            MemoryScopeSettingModel.enabled.is_(True),
        )
        .order_by(MemorySourceDelivery.sequence)
        .limit(limit)
    ).all()
    writer = MemoryWriteLifecycleService(
        SqlAlchemyMemoryRepository(session),
        SqlAlchemyMemorySourceEvidenceReader(session),
    )
    for row in rows:
        setting = session.get(MemoryScopeSettingModel, row.scope_setting_id)
        scope = MemoryScope(
            setting.owner_id, setting.world_id, setting.subject_world_character_id
        )
        try:
            result = writer.propose_candidate(
                scope=scope,
                source_type=MemorySourceTypeV1(row.source_type),
                source_id=row.source_id,
                memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
            )
        except MemoryDomainError:
            # A departed subject or conflicting source cannot poison later
            # scopes. Database failures still roll back and resume next tick.
            row.state, row.reason_code = "invalidated", "memory_source_unavailable"
            continue
        if result.candidate is None:
            row.state, row.reason_code = "invalidated", result.code
        else:
            row.state, row.candidate_id = "delivered", result.candidate.id
    session.commit()
    return len(rows)


def enqueue_scope(
    session,
    *,
    scope_setting_id: str,
    trigger: str,
    now: datetime,
    cutoff: int | None = None,
    requested_at: datetime | None = None,
) -> int:
    repo = SqlAlchemyMemoryBatchRepository(session)
    setting = session.get(MemoryScopeSettingModel, scope_setting_id)
    if setting is None:
        return 0
    if cutoff is None:
        cutoff = (
            session.scalar(
                select(func.max(MemorySourceDelivery.sequence)).where(
                    MemorySourceDelivery.scope_setting_id == scope_setting_id
                )
            )
            or 0
        )
    # Filter assigned entries before the cap; failed heads cannot starve tails.
    rows = (
        session.scalars(
            select(MemoryCandidate)
            .join(
                MemorySourceDelivery,
                MemorySourceDelivery.candidate_id == MemoryCandidate.id,
            )
            .where(
                MemorySourceDelivery.scope_setting_id == scope_setting_id,
                or_(
                    MemorySourceDelivery.sequence <= cutoff,
                    False
                    if requested_at is None
                    else MemorySourceDelivery.captured_at <= requested_at,
                ),
                MemorySourceDelivery.batch_job_id.is_(None),
                MemoryCandidate.status == "pending",
            )
            .order_by(MemorySourceDelivery.sequence)
            .limit(32)
        )
        .unique()
        .all()
    )
    scope = MemoryScope(
        setting.owner_id, setting.world_id, setting.subject_world_character_id
    )
    reader = SqlAlchemyMemorySourceEvidenceReader(session)
    groups = defaultdict(list)
    for candidate in rows:
        evidence = reader.read_evidence(
            scope=scope,
            source_type=MemorySourceTypeV1(candidate.source_type),
            source_id=candidate.source_id,
        )
        size = (
            0
            if evidence is None
            else len(
                (
                    evidence.deterministic_summary + (evidence.subjective_context or "")
                ).encode("utf-8")
            )
        )
        groups[None if evidence is None else evidence.thread_id].append(
            (candidate.id, size)
        )
    jobs = 0
    for group in groups.values():
        chunks, chunk, size = [], [], 0
        for candidate_id, candidate_size in group:
            if chunk and (
                len(chunk) >= MAX_SELECTION_CANDIDATES
                or size + candidate_size > MAX_SELECTION_INPUT_UTF8_BYTES
            ):
                chunks.append(tuple(chunk))
                chunk, size = [], 0
            chunk.append(candidate_id)
            size += candidate_size
        if chunk:
            chunks.append(tuple(chunk))
        for chunk in chunks:
            jobs += (
                repo.enqueue(
                    scope_setting_id=scope_setting_id,
                    candidate_ids=chunk,
                    cutoff=cutoff,
                    trigger=trigger,
                    now=now,
                )
                is not None
            )
    return jobs


def schedule_batches(session, *, now: datetime, shutdown: bool = False) -> None:
    # Authorize the cutoff once, in one SQL statement even for many characters.
    # Recovery may later deliver holes inside this persisted time boundary.
    config_table = MemoryBatchSetting.__table__
    scope_table = MemoryScopeSettingModel.__table__
    consent = (MemoryBatchSetting.ai_enabled.is_(True)) & (
        MemoryBatchSetting.consent_version == "memory-selection-consent.v1"
    )
    live_scope = exists(
        select(scope_table.c.id).where(
            scope_table.c.id == config_table.c.scope_setting_id,
            scope_table.c.enabled.is_(True),
        )
    )
    if shutdown:
        session.execute(
            update(MemoryBatchSetting)
            .where(consent, live_scope, MemoryBatchSetting.shutdown_enabled.is_(True))
            .values(trigger_kind="shutdown", trigger_requested_at=now)
        )
        session.flush()
    deliveries = MemorySourceDelivery.__table__
    ready_source = exists(
        select(deliveries.c.sequence).where(
            deliveries.c.scope_setting_id == config_table.c.scope_setting_id,
            deliveries.c.state == "delivered",
            deliveries.c.batch_job_id.is_(None),
            or_(
                deliveries.c.sequence <= config_table.c.trigger_cutoff,
                deliveries.c.captured_at <= config_table.c.trigger_requested_at,
            ),
        )
    )
    worlds = Base.metadata.tables["worlds"]
    due_slot = (MemoryBatchSetting.schedule_enabled.is_(True)) & (
        MemoryBatchSetting.next_due_at <= now
    )
    configs = session.scalars(
        select(MemoryBatchSetting)
        .join(
            MemoryScopeSettingModel,
            MemoryScopeSettingModel.id == MemoryBatchSetting.scope_setting_id,
        )
        .join(worlds, worlds.c.id == MemoryScopeSettingModel.world_id)
        .where(
            consent,
            MemoryScopeSettingModel.enabled.is_(True),
            or_(
                due_slot,
                MemoryBatchSetting.timezone != worlds.c.timezone,
                ready_source & MemoryBatchSetting.trigger_kind.is_not(None),
            ),
        )
        .order_by(
            MemoryBatchSetting.last_claimed_at.asc().nullsfirst(),
            MemoryBatchSetting.scope_setting_id,
        )
        .limit(32)
    ).all()
    for config in configs:
        setting = session.get(MemoryScopeSettingModel, config.scope_setting_id)
        scope = MemoryScope(
            setting.owner_id, setting.world_id, setting.subject_world_character_id
        )
        try:
            zone = SqlAlchemyMemoryBatchRepository(session).timezone(scope)
        except MemoryDomainError:
            # Preserve user settings but rotate unavailable scopes behind the
            # next bounded scan, without authorizing a provider request.
            config.last_claimed_at = now
            continue
        consumed = (
            None
            if config.last_consumed_date is None
            else date.fromisoformat(config.last_consumed_date)
        )
        if config.timezone != zone:
            config.timezone, config.version = zone, config.version + 1
            config.next_due_at = next_daily_slot(
                after=now,
                local_time=config.local_time,
                timezone=zone,
                last_consumed_date=consumed,
            )
        due = (
            config.schedule_enabled
            and config.next_due_at is not None
            and as_utc(config.next_due_at) <= as_utc(now)
        )
        if due:
            latest = (
                session.scalar(
                    select(func.max(MemorySourceDelivery.sequence)).where(
                        MemorySourceDelivery.scope_setting_id == config.scope_setting_id
                    )
                )
                or 0
            )
            config.trigger_cutoff = max(config.trigger_cutoff, latest)
            config.trigger_kind, config.trigger_requested_at = "scheduled", now
            config.last_consumed_date = (
                as_utc(now).astimezone(schedule_timezone(zone)).date().isoformat()
            )
            config.next_due_at = next_daily_slot(
                after=now,
                local_time=config.local_time,
                timezone=zone,
                last_consumed_date=date.fromisoformat(config.last_consumed_date),
            )
        if config.trigger_kind:
            enqueue_scope(
                session,
                scope_setting_id=config.scope_setting_id,
                trigger=config.trigger_kind,
                now=now,
                cutoff=config.trigger_cutoff,
                requested_at=config.trigger_requested_at,
            )
    session.commit()


def rebuild_briefs(session, *, now: datetime, source_reader=None) -> None:
    repository = SqlAlchemyMemoryConsolidationRepository(session)
    reader = source_reader or SqlAlchemyMemorySourceEvidenceReader(session)
    memory = SqlAlchemyMemoryRepository(session)
    configs = session.scalars(
        select(MemoryBatchSetting)
        .join(
            MemoryScopeSettingModel,
            MemoryScopeSettingModel.id == MemoryBatchSetting.scope_setting_id,
        )
        .where(
            MemoryBatchSetting.brief_dirty.is_(True),
            MemoryScopeSettingModel.enabled.is_(True),
        )
        .limit(16)
    ).all()
    for config in configs:
        snapshot = repository.get_scope_setting_by_id(config.scope_setting_id)
        try:
            memory.validate_scope(snapshot.scope)
        except MemoryDomainError:
            continue
        items = repository.hot_brief_source_items(setting=snapshot, now=now, limit=24)
        valid = True
        for item in items:
            evidence_rows = memory.list_item_evidence(
                scope=snapshot.scope, item_id=item.id
            )
            if not evidence_rows:
                valid = False
            for evidence in evidence_rows:
                fresh = reader.read_evidence(
                    scope=snapshot.scope,
                    source_type=evidence.source_type,
                    source_id=evidence.source_id,
                )
                if (
                    fresh is None
                    or fresh.source_digest != evidence.source_digest
                    or memory_evidence_blocked_code(
                        scope=snapshot.scope,
                        source_type=evidence.source_type,
                        source_id=evidence.source_id,
                        evidence=fresh,
                    )
                ):
                    valid = False
        if not valid:
            # Do not silently delete owner memories or compress stale evidence.
            # The durable dirty flag retries this code-only step; read-side
            # validation also excludes any stale previously generated brief.
            continue
        if items:
            repository.replace_hot_brief(
                setting=snapshot,
                expected_source_items=items,
                summary=deterministic_hot_brief(items),
                contract_version=MEMORY_HOT_BRIEF_CONTRACT_VERSION,
                now=now,
            )
        config.brief_dirty = False
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
            deliver_candidates(db)
            schedule_batches(db, now=now, shutdown=shutdown)
        try:
            with self.session_factory() as db:
                rebuild_briefs(db, now=datetime.now(UTC))
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
