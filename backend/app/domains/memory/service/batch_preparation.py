"""Candidate delivery, bounded selection groups and canonical hot-brief rebuilds.

Each function preserves the original transaction boundary. Runtime supplies
canonical source readers against the same Session and schedules these services.
"""
from collections import defaultdict
from datetime import datetime
from sqlalchemy import func, or_, select

from app.domains.memory.contracts.batch_preparation import MemoryPreparationDependencies
from app.domains.memory.policies.batch import MAX_SELECTION_CANDIDATES, MAX_SELECTION_INPUT_UTF8_BYTES
from app.domains.memory.policies.consolidation import deterministic_hot_brief, MEMORY_HOT_BRIEF_CONTRACT_VERSION
from app.domains.memory.contracts.provenance import MemoryKindV1, MemorySourceTypeV1
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryDomainError
from app.domains.memory.models.batch import MemoryBatchSetting, MemorySourceDelivery
from app.domains.memory.models.items import MemoryCandidate, MemoryScopeSettingModel
from app.domains.memory.service.items import MemoryWriteLifecycleService, memory_evidence_blocked_code


def deliver_candidates(session, *, dependencies: MemoryPreparationDependencies, limit: int = 128) -> int:
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
        dependencies.memory_repository(session),
        dependencies.source_reader(session),
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
    dependencies: MemoryPreparationDependencies,
    scope_setting_id: str,
    trigger: str,
    now: datetime,
    cutoff: int | None = None,
    requested_at: datetime | None = None,
) -> int:
    repo = dependencies.batch_repository(session)
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
    reader = dependencies.source_reader(session)
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



def rebuild_briefs(session, *, dependencies: MemoryPreparationDependencies, now: datetime, source_reader=None) -> None:
    repository = dependencies.consolidation_repository(session)
    reader = source_reader or dependencies.source_reader(session)
    memory = dependencies.memory_repository(session)
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
