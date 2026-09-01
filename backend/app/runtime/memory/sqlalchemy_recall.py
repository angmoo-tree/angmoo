"""Canonical SQLAlchemy read adapters for bounded Memory recall."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.domains.characters.public import Character
from app.domains.memory.infrastructure import (
    MemoryItem,
    MemoryItemEvidence,
    MemoryScopeSettingModel,
)
from app.domains.memory.public import (
    CanonicalMemoryEvidence,
    CanonicalRecallOperation,
    CanonicalRecallQuery,
    CanonicalRecallRecord,
    MemoryItemStatus,
    MemoryRecallCandidate,
    MemoryRecallDocument,
    MemoryScope,
    MemorySourceTypeV1,
    RecallDocumentKind,
    SOURCE_KIND_BY_TYPE,
)
from app.runtime.memory.sqlalchemy_source_reader import (
    SqlAlchemyMemorySourceEvidenceReader,
    models as source_models,
)


class SqlAlchemyMemoryRecallDocumentSource:
    """Materialize only accepted, current, observable canonical Memory evidence."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now_factory=lambda: datetime.now(UTC),
    ) -> None:
        self._factory = session_factory
        self._now_factory = now_factory

    def all_documents(self) -> tuple[MemoryRecallDocument, ...]:
        item_ids = self.all_item_ids()
        documents = self.documents_for_item_ids(item_ids)
        return tuple(
            document
            for item_id in sorted(documents)
            for document in documents[item_id]
        )

    def all_item_ids(self) -> tuple[str, ...]:
        with self._factory() as session:
            return tuple(
                session.scalars(select(MemoryItem.id).order_by(MemoryItem.id))
            )

    def documents_for_item_ids(
        self,
        item_ids: Iterable[str],
    ) -> dict[str, tuple[MemoryRecallDocument, ...]]:
        ids = tuple(dict.fromkeys(str(value) for value in item_ids if value))
        if not ids:
            return {}
        now = _as_utc(self._now_factory())
        with self._factory() as session:
            items = list(
                session.scalars(
                    select(MemoryItem)
                    .where(MemoryItem.id.in_(ids))
                    .order_by(MemoryItem.id)
                )
            )
            evidence_by_item: dict[str, list[MemoryItemEvidence]] = {}
            for evidence in session.scalars(
                select(MemoryItemEvidence)
                .where(MemoryItemEvidence.memory_item_id.in_(ids))
                .order_by(
                    MemoryItemEvidence.memory_item_id,
                    MemoryItemEvidence.id,
                )
            ):
                evidence_by_item.setdefault(evidence.memory_item_id, []).append(evidence)
            reader = SqlAlchemyMemorySourceEvidenceReader(session)
            result: dict[str, tuple[MemoryRecallDocument, ...]] = {}
            for item in items:
                result[item.id] = self._documents_for_item(
                    session=session,
                    reader=reader,
                    item=item,
                    evidences=evidence_by_item.get(item.id, []),
                    now=now,
                )
            return result

    def item_ids_for_scope_setting(
        self,
        setting_id: str,
    ) -> tuple[str, ...]:
        with self._factory() as session:
            setting = session.get(MemoryScopeSettingModel, setting_id)
            if setting is None:
                return ()
            return tuple(
                session.scalars(
                    select(MemoryItem.id)
                    .where(
                        MemoryItem.owner_id == setting.owner_id,
                        MemoryItem.world_id == setting.world_id,
                        MemoryItem.subject_world_character_id
                        == setting.subject_world_character_id,
                    )
                    .order_by(MemoryItem.id)
                )
            )

    def scope_setting(
        self,
        setting_id: str,
    ) -> tuple[MemoryScope, bool] | None:
        with self._factory() as session:
            setting = session.get(MemoryScopeSettingModel, setting_id)
            if setting is None:
                return None
            return (
                MemoryScope(
                    owner_id=setting.owner_id,
                    world_id=setting.world_id,
                    subject_world_character_id=setting.subject_world_character_id,
                ),
                bool(setting.enabled),
            )

    @staticmethod
    def _documents_for_item(
        *,
        session: Session,
        reader: SqlAlchemyMemorySourceEvidenceReader,
        item: MemoryItem,
        evidences: list[MemoryItemEvidence],
        now: datetime,
    ) -> tuple[MemoryRecallDocument, ...]:
        scope = _item_scope(item)
        setting = _scope_setting(session, scope)
        if setting is None or not setting.enabled or not _item_retrievable(item, now):
            return ()
        current: list[tuple[MemoryItemEvidence, CanonicalMemoryEvidence]] = []
        for row in evidences:
            canonical = _current_evidence(reader, scope, item, row)
            if canonical is not None:
                current.append((row, canonical))
        if not current:
            return ()

        occurred_at = max(value.source_created_at for _row, value in current)
        evidence_ids = ",".join(row.id for row, _value in current)
        documents: list[MemoryRecallDocument] = [
            MemoryRecallDocument(
                document_id=f"memory-item:{item.id}",
                memory_item_id=item.id,
                owner_id=item.owner_id,
                world_id=item.world_id,
                subject_world_character_id=item.subject_world_character_id,
                counterpart_world_character_id=item.counterpart_world_character_id,
                thread_id=item.thread_id,
                kind=RecallDocumentKind.MEMORY_ITEM,
                canonical_source_id=item.id,
                occurred_at=occurred_at,
                text=item.summary,
                metadata={
                    "memory_kind": item.memory_kind,
                    "item_version": str(item.version),
                    "evidence_ids": evidence_ids,
                },
            )
        ]
        for row, canonical in current:
            documents.append(
                MemoryRecallDocument(
                    document_id=f"memory-source:{item.id}:{row.id}",
                    memory_item_id=item.id,
                    owner_id=item.owner_id,
                    world_id=item.world_id,
                    subject_world_character_id=item.subject_world_character_id,
                    counterpart_world_character_id=(
                        canonical.counterpart_world_character_id
                    ),
                    thread_id=canonical.thread_id,
                    kind=SOURCE_KIND_BY_TYPE[canonical.source_type],
                    canonical_source_id=canonical.source_id,
                    source_type=canonical.source_type,
                    source_event_id=canonical.source_event_id,
                    occurred_at=canonical.source_created_at,
                    text=canonical.deterministic_summary,
                    metadata={
                        "evidence_id": row.id,
                        "source_digest": row.source_digest,
                        "memory_kind": item.memory_kind,
                        "item_version": str(item.version),
                    },
                )
            )
        return tuple(documents)


class SqlAlchemyCanonicalRecallRepository:
    """Hydrate and revalidate every projection candidate against canonical rows."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._factory = session_factory

    def memory_enabled(self, scope: MemoryScope) -> bool:
        with self._factory() as session:
            setting = _scope_setting(session, scope)
            return bool(setting and setting.enabled)

    def revalidate_candidates(
        self,
        *,
        scope: MemoryScope,
        candidates: tuple[MemoryRecallCandidate, ...],
        now: datetime,
    ) -> tuple[CanonicalRecallRecord, ...]:
        if not candidates:
            return ()
        with self._factory() as session:
            setting = _scope_setting(session, scope)
            if setting is None or not setting.enabled:
                return ()
            reader = SqlAlchemyMemorySourceEvidenceReader(session)
            records: list[CanonicalRecallRecord] = []
            seen: set[str] = set()
            for candidate in candidates:
                if candidate.document_id in seen:
                    continue
                item = session.get(MemoryItem, candidate.memory_item_id)
                if (
                    item is None
                    or _item_scope(item) != scope
                    or not _item_retrievable(item, _as_utc(now))
                ):
                    continue
                evidences = list(
                    session.scalars(
                        select(MemoryItemEvidence)
                        .where(MemoryItemEvidence.memory_item_id == item.id)
                        .order_by(MemoryItemEvidence.id)
                    )
                )
                current = [
                    (row, canonical)
                    for row in evidences
                    if (
                        canonical := _current_evidence(reader, scope, item, row)
                    )
                    is not None
                ]
                if not current:
                    continue
                record = _candidate_record(candidate, item, current)
                if record is None:
                    continue
                seen.add(candidate.document_id)
                records.append(record)
            return tuple(records)

    def execute_direct(
        self,
        *,
        query: CanonicalRecallQuery,
        now: datetime,
    ) -> tuple[CanonicalRecallRecord, ...]:
        with self._factory() as session:
            setting = _scope_setting(session, query.scope)
            if setting is None or not setting.enabled:
                return ()
            if query.operation is CanonicalRecallOperation.GET_CHARACTER_SUMMARIES:
                return self._character_summaries(session, query)

            source_types = _operation_source_types(query.operation)
            statement = (
                select(MemoryItemEvidence, MemoryItem)
                .join(MemoryItem, MemoryItem.id == MemoryItemEvidence.memory_item_id)
                .where(
                    MemoryItem.owner_id == query.scope.owner_id,
                    MemoryItem.world_id == query.scope.world_id,
                    MemoryItem.subject_world_character_id
                    == query.scope.subject_world_character_id,
                    MemoryItem.status == MemoryItemStatus.ACTIVE.value,
                    MemoryItem.deleted_at.is_(None),
                    MemoryItem.superseded_by_id.is_(None),
                )
                .order_by(
                    MemoryItemEvidence.source_created_at.desc(),
                    MemoryItemEvidence.id,
                )
            )
            if source_types:
                statement = statement.where(
                    MemoryItemEvidence.source_type.in_(
                        tuple(value.value for value in source_types)
                    )
                )
            rows = list(session.execute(statement))
            reader = SqlAlchemyMemorySourceEvidenceReader(session)
            records: list[CanonicalRecallRecord] = []
            seen: set[str] = set()
            for evidence, item in rows:
                if not _item_retrievable(item, _as_utc(now)):
                    continue
                if query.counterpart_world_character_id is not None and (
                    item.counterpart_world_character_id
                    != query.counterpart_world_character_id
                ):
                    continue
                if query.thread_id is not None and item.thread_id != query.thread_id:
                    continue
                if query.source_references and not _reference_matches(
                    evidence,
                    query.source_references,
                ):
                    continue
                canonical = _current_evidence(reader, query.scope, item, evidence)
                if canonical is None or not _in_time_range(
                    canonical.source_created_at,
                    query,
                ):
                    continue
                reference = _source_reference(canonical.source_type, canonical.source_id)
                if reference in seen:
                    continue
                seen.add(reference)
                records.append(
                    _canonical_source_record(
                        reference=reference,
                        item=item,
                        evidence=evidence,
                        canonical=canonical,
                    )
                )
                if len(records) >= query.limit:
                    break
            return tuple(records)

    @staticmethod
    def _character_summaries(
        session: Session,
        query: CanonicalRecallQuery,
    ) -> tuple[CanonicalRecallRecord, ...]:
        requested = tuple(dict.fromkeys(query.world_character_references))
        rows = list(
            session.execute(
                select(source_models.WorldCharacter, Character)
                .join(
                    Character,
                    Character.id == source_models.WorldCharacter.character_id,
                )
                .join(
                    source_models.WorldMembership,
                    source_models.WorldMembership.id
                    == source_models.WorldCharacter.membership_id,
                )
                .where(
                    source_models.WorldCharacter.id.in_(requested),
                    source_models.WorldCharacter.world_id == query.scope.world_id,
                    source_models.WorldCharacter.status == "active",
                    source_models.WorldMembership.status == "active",
                )
                .order_by(source_models.WorldCharacter.id)
                .limit(query.limit)
            )
        )
        blocked = set(
            session.scalars(
                select(source_models.WorldCharacterBlock.blocked_world_character_id).where(
                    source_models.WorldCharacterBlock.world_id == query.scope.world_id,
                    source_models.WorldCharacterBlock.blocker_world_character_id
                    == query.scope.subject_world_character_id,
                )
            )
        ) | set(
            session.scalars(
                select(source_models.WorldCharacterBlock.blocker_world_character_id).where(
                    source_models.WorldCharacterBlock.world_id == query.scope.world_id,
                    source_models.WorldCharacterBlock.blocked_world_character_id
                    == query.scope.subject_world_character_id,
                )
            )
        )
        records: list[CanonicalRecallRecord] = []
        for world_character, character in rows:
            if world_character.id in blocked:
                continue
            text = " ".join(
                value
                for value in (
                    character.name,
                    character.one_liner,
                    character.persona_summary,
                )
                if value
            )
            records.append(
                CanonicalRecallRecord(
                    reference=f"world-character:{world_character.id}",
                    kind=RecallDocumentKind.CHARACTER_SUMMARY,
                    canonical_source_id=world_character.id,
                    text=text,
                    occurred_at=_as_utc(world_character.updated_at),
                    counterpart_world_character_id=world_character.id,
                    metadata={"character_id": character.id},
                )
            )
        return tuple(records)


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


def _scope_setting(
    session: Session,
    scope: MemoryScope,
) -> MemoryScopeSettingModel | None:
    return session.scalar(
        select(MemoryScopeSettingModel).where(
            MemoryScopeSettingModel.owner_id == scope.owner_id,
            MemoryScopeSettingModel.world_id == scope.world_id,
            MemoryScopeSettingModel.subject_world_character_id
            == scope.subject_world_character_id,
        )
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
    reader: SqlAlchemyMemorySourceEvidenceReader,
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


__all__ = [
    "SqlAlchemyCanonicalRecallRepository",
    "SqlAlchemyMemoryRecallDocumentSource",
]
