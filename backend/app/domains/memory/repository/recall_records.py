"""Hydrate canonical Memory records and validate their current evidence snapshots."""
from __future__ import annotations
from datetime import UTC, datetime
from typing import Any
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.contracts.recall import (
    CanonicalRecallOperation, CanonicalRecallQuery, CanonicalRecallRecord,
    MemoryRecallCandidate, MemoryRecallDocument, RecallDocumentKind, SOURCE_KIND_BY_TYPE,
)
from app.domains.memory.contracts.provenance import MemoryItemStatus, MemorySourceTypeV1
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence, MemorySourceEvidenceReaderPort


def _candidate_record(
    candidate: MemoryRecallCandidate,
    item: MemoryItem,
    current: list[tuple[MemoryItemEvidence, CanonicalMemoryEvidence]],
) -> CanonicalRecallRecord | None:
    evidence_references = tuple(
        _source_reference(value.source_type, value.source_id)
        for _row, value in current
    )
    if candidate.kind is RecallDocumentKind.MEMORY_ITEM:
        if (
            candidate.document_id != f"memory-item:{item.id}"
            or candidate.canonical_source_id != item.id
            or candidate.counterpart_world_character_id
            != item.counterpart_world_character_id
            or candidate.thread_id != item.thread_id
        ):
            return None
        return CanonicalRecallRecord(
            reference=candidate.document_id,
            kind=RecallDocumentKind.MEMORY_ITEM,
            canonical_source_id=item.id,
            text=item.summary,
            occurred_at=max(value.source_created_at for _row, value in current),
            memory_item_id=item.id,
            counterpart_world_character_id=item.counterpart_world_character_id,
            thread_id=item.thread_id,
            evidence_references=evidence_references,
            metadata={"memory_kind": item.memory_kind, "item_version": str(item.version)},
        )

    evidence_id = candidate.metadata.get("evidence_id")
    for row, canonical in current:
        if row.id != evidence_id:
            continue
        if (
            candidate.document_id != f"memory-source:{item.id}:{row.id}"
            or candidate.kind is not SOURCE_KIND_BY_TYPE[canonical.source_type]
            or candidate.canonical_source_id != canonical.source_id
            or candidate.source_type is not canonical.source_type
            or candidate.source_event_id != canonical.source_event_id
            or candidate.counterpart_world_character_id
            != canonical.counterpart_world_character_id
            or candidate.thread_id != canonical.thread_id
            or candidate.metadata.get("source_digest") != row.source_digest
        ):
            return None
        return _canonical_source_record(
            reference=candidate.document_id,
            item=item,
            evidence=row,
            canonical=canonical,
        )
    return None



def _canonical_source_record(
    *,
    reference: str,
    item: MemoryItem,
    evidence: MemoryItemEvidence,
    canonical: CanonicalMemoryEvidence,
) -> CanonicalRecallRecord:
    return CanonicalRecallRecord(
        reference=reference,
        kind=SOURCE_KIND_BY_TYPE[canonical.source_type],
        canonical_source_id=canonical.source_id,
        text=canonical.deterministic_summary,
        occurred_at=_as_utc(canonical.source_created_at),
        memory_item_id=item.id,
        counterpart_world_character_id=canonical.counterpart_world_character_id,
        thread_id=canonical.thread_id,
        source_type=canonical.source_type,
        source_event_id=canonical.source_event_id,
        evidence_references=(
            _source_reference(canonical.source_type, canonical.source_id),
        ),
        metadata={
            "evidence_id": evidence.id,
            "source_digest": evidence.source_digest,
            "memory_kind": item.memory_kind,
        },
    )



def _item_scope(item: MemoryItem) -> MemoryScope:
    return MemoryScope(
        owner_id=item.owner_id,
        world_id=item.world_id,
        subject_world_character_id=item.subject_world_character_id,
    )



def _item_retrievable(item: MemoryItem, now: datetime) -> bool:
    return (
        item.status == MemoryItemStatus.ACTIVE.value
        and item.deleted_at is None
        and item.superseded_by_id is None
        and _as_utc(item.valid_from) <= now
        and (item.valid_until is None or _as_utc(item.valid_until) > now)
    )



def _current_evidence(
    reader: MemorySourceEvidenceReaderPort,
    scope: MemoryScope,
    item: MemoryItem,
    evidence: MemoryItemEvidence,
) -> CanonicalMemoryEvidence | None:
    try:
        source_type = MemorySourceTypeV1(evidence.source_type)
    except ValueError:
        return None
    canonical = reader.read_evidence(
        scope=scope,
        source_type=source_type,
        source_id=evidence.source_id,
    )
    if canonical is None:
        return None
    if (
        canonical.source_type is not source_type
        or canonical.source_id != evidence.source_id
        or canonical.source_world_id != scope.world_id
        or canonical.source_digest != evidence.source_digest
        or not canonical.successful
        or not canonical.visible
        or not canonical.observed_by_subject
        or not canonical.membership_active
        or canonical.blocked
    ):
        return None
    if (
        item.counterpart_world_character_id is not None
        and canonical.counterpart_world_character_id
        != item.counterpart_world_character_id
    ):
        return None
    if item.thread_id is not None and canonical.thread_id != item.thread_id:
        return None
    return canonical



def _operation_source_types(
    operation: CanonicalRecallOperation,
) -> tuple[MemorySourceTypeV1, ...]:
    if operation is CanonicalRecallOperation.LIST_SOCIAL_EVENTS:
        return (MemorySourceTypeV1.SOCIAL_EVENT,)
    if operation is CanonicalRecallOperation.LIST_ACTIVITY_EPISODES:
        return (MemorySourceTypeV1.ACTIVITY_EVENT,)
    if operation is CanonicalRecallOperation.LIST_RELATIONSHIP_CHANGES:
        return (MemorySourceTypeV1.RELATIONSHIP_EVENT,)
    if operation is CanonicalRecallOperation.GET_POST_THREAD:
        return (MemorySourceTypeV1.POST, MemorySourceTypeV1.REPLY)
    return ()



def _reference_matches(
    evidence: MemoryItemEvidence,
    references: tuple[str, ...],
) -> bool:
    values = {
        evidence.id,
        evidence.source_id,
        evidence.source_event_id,
        _source_reference(MemorySourceTypeV1(evidence.source_type), evidence.source_id),
    }
    return any(reference in values for reference in references)



def _source_reference(source_type: MemorySourceTypeV1, source_id: str) -> str:
    return f"source:{source_type.value}:{source_id}"



def _in_time_range(value: datetime, query: CanonicalRecallQuery) -> bool:
    occurred = _as_utc(value)
    if query.occurred_from is not None and occurred < _as_utc(query.occurred_from):
        return False
    if query.occurred_to is not None and occurred >= _as_utc(query.occurred_to):
        return False
    return True



def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
