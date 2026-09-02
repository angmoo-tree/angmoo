"""SQLAlchemy adapter for canonical Memory scope, writes, and lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import Base
from app.domains.memory.domain.errors import (
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryScopeError,
)
from app.domains.memory.domain.lifecycle import (
    MemoryCandidateRecord,
    MemoryItemRecord,
)
from app.domains.memory.domain.provenance import (
    MemoryCandidateStatus,
    MemoryHotBriefStatus,
    MemoryItemStatus,
    MemoryJobStatus,
    MemoryKindV1,
    MemoryProviderMode,
    MemorySourceTypeV1,
)
from app.domains.memory.domain.retention import (
    DEFAULT_MEMORY_RETENTION_DAYS,
    is_memory_expired,
)
from app.domains.memory.domain.scope import MemoryScope, MemoryScopeSetting
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MemoryCandidate,
    MemoryHotBrief,
    MemoryItem,
    MemoryItemEvidence,
    MemoryMaintenanceJob,
    MemoryScopeSettingModel,
)
from app.domains.memory.ports.source_reader import CanonicalMemoryEvidence


class SqlAlchemyMemoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def validate_scope(self, scope: MemoryScope) -> None:
        self._validate_scope(scope)

    def get_scope_setting(self, scope: MemoryScope) -> MemoryScopeSetting | None:
        row = self._find_scope(scope)
        return None if row is None else self._to_scope(row)

    def get_or_create_scope_setting(
        self,
        scope: MemoryScope,
    ) -> MemoryScopeSetting:
        self._validate_scope(scope)
        existing = self._find_scope(scope)
        if existing is not None:
            return self._to_scope(existing)
        row = MemoryScopeSettingModel(
            id=str(uuid4()),
            owner_id=scope.owner_id,
            world_id=scope.world_id,
            subject_world_character_id=scope.subject_world_character_id,
            enabled=False,
            retention_days=DEFAULT_MEMORY_RETENTION_DAYS,
            provider_mode=MemoryProviderMode.NONE.value,
            version=1,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            existing = self._find_scope(scope)
            if existing is None:
                raise MemoryConflictError("memory_scope_create_conflict") from None
            return self._to_scope(existing)
        self._session.refresh(row)
        return self._to_scope(row)

    def update_scope_setting(
        self,
        scope: MemoryScope,
        *,
        expected_version: int,
        enabled: bool,
        retention_days: int,
        provider_mode: MemoryProviderMode,
    ) -> MemoryScopeSetting:
        self._validate_scope(scope)
        if expected_version < 1:
            raise MemoryConflictError("memory_scope_version_conflict")
        statement = (
            update(MemoryScopeSettingModel)
            .where(
                MemoryScopeSettingModel.owner_id == scope.owner_id,
                MemoryScopeSettingModel.world_id == scope.world_id,
                MemoryScopeSettingModel.subject_world_character_id
                == scope.subject_world_character_id,
                MemoryScopeSettingModel.version == expected_version,
            )
            .values(
                enabled=enabled,
                retention_days=retention_days,
                provider_mode=provider_mode.value,
                version=expected_version + 1,
            )
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            raise MemoryConflictError("memory_scope_version_conflict")
        self._session.flush()
        updated = self._find_scope(scope, populate_existing=True)
        if updated is None:
            raise MemoryConflictError("memory_scope_update_missing")
        if not enabled:
            self._invalidate_hot_briefs(updated.id, now=datetime.now(UTC))
            self._session.flush()
        return self._to_scope(updated)

    def upsert_candidate(
        self,
        *,
        setting: MemoryScopeSetting,
        evidence: CanonicalMemoryEvidence,
        memory_kind: MemoryKindV1,
        idempotency_key: str,
    ) -> tuple[MemoryCandidateRecord, bool]:
        self._require_setting(setting)
        existing = self._find_candidate_by_key(
            setting_id=setting.id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            self._assert_candidate_replay(existing, evidence, memory_kind)
            return self._to_candidate(existing), False
        row = MemoryCandidate(
            id=str(uuid4()),
            scope_setting_id=setting.id,
            source_type=evidence.source_type.value,
            source_id=evidence.source_id,
            source_digest=evidence.source_digest,
            memory_kind_hint=memory_kind.value,
            status=MemoryCandidateStatus.PENDING.value,
            idempotency_key=idempotency_key,
            version=1,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            existing = self._find_candidate_by_key(
                setting_id=setting.id,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise MemoryConflictError("memory_candidate_create_conflict") from None
            self._assert_candidate_replay(existing, evidence, memory_kind)
            return self._to_candidate(existing), False
        self._session.refresh(row)
        return self._to_candidate(row), True

    def get_candidate(
        self,
        *,
        scope: MemoryScope,
        candidate_id: str,
    ) -> MemoryCandidateRecord:
        return self._to_candidate(self._require_candidate(scope, candidate_id))

    def reject_candidate(
        self,
        *,
        scope: MemoryScope,
        candidate_id: str,
        expected_version: int,
        reason_code: str,
        decided_at: datetime,
    ) -> MemoryCandidateRecord:
        row = self._require_candidate(scope, candidate_id, for_update=True)
        if row.status == MemoryCandidateStatus.REJECTED.value:
            if row.reason_code != reason_code:
                raise MemoryConflictError("memory_candidate_decision_conflict")
            return self._to_candidate(row)
        if row.status != MemoryCandidateStatus.PENDING.value or row.version != expected_version:
            raise MemoryConflictError("memory_candidate_version_conflict")
        row.status = MemoryCandidateStatus.REJECTED.value
        row.reason_code = reason_code
        row.decided_at = decided_at
        row.version += 1
        self._session.flush()
        return self._to_candidate(row)

    def accept_candidate(
        self,
        *,
        setting: MemoryScopeSetting,
        candidate_id: str,
        expected_candidate_version: int,
        evidence: CanonicalMemoryEvidence,
        memory_kind: MemoryKindV1,
        summary: str,
        confidence: float,
        salience: float,
        valid_from: datetime,
        valid_until: datetime | None,
        now: datetime,
        enqueue_maintenance: bool = True,
    ) -> tuple[MemoryCandidateRecord, MemoryItemRecord, bool]:
        self._require_setting(setting)
        candidate = self._require_candidate(
            setting.scope,
            candidate_id,
            for_update=True,
        )
        if candidate.status == MemoryCandidateStatus.ACCEPTED.value:
            item = self._find_item_for_candidate(setting.scope, candidate)
            if item is None:
                raise MemoryConflictError("memory_candidate_item_missing")
            return self._to_candidate(candidate), self._to_item(item), False
        self._require_pending_candidate(
            candidate,
            expected_version=expected_candidate_version,
            evidence=evidence,
            memory_kind=memory_kind,
        )
        with self._session.begin_nested():
            item = self._new_item(
                setting=setting,
                evidence=evidence,
                memory_kind=memory_kind,
                summary=summary,
                confidence=confidence,
                salience=salience,
                valid_from=valid_from,
                valid_until=valid_until,
            )
            self._session.add(item)
            self._session.flush()
            self._session.add(self._new_evidence(item.id, evidence))
            candidate.status = MemoryCandidateStatus.ACCEPTED.value
            candidate.reason_code = None
            candidate.decided_at = now
            candidate.version += 1
            self._invalidate_hot_briefs(setting.id, now=now)
            if enqueue_maintenance:
                self._enqueue_job(
                    setting.id,
                    reason="memory_item_accepted",
                    idempotency_key=f"memory-item:{item.id}:accepted:v1",
                )
            self._session.flush()
        self._session.refresh(item)
        return self._to_candidate(candidate), self._to_item(item), True

    def correct_item(
        self,
        *,
        setting: MemoryScopeSetting,
        old_item_id: str,
        expected_item_version: int,
        candidate_id: str,
        expected_candidate_version: int,
        evidence: CanonicalMemoryEvidence,
        memory_kind: MemoryKindV1,
        summary: str,
        confidence: float,
        salience: float,
        valid_from: datetime,
        valid_until: datetime | None,
        now: datetime,
    ) -> tuple[MemoryCandidateRecord, MemoryItemRecord]:
        self._require_setting(setting)
        old_item = self._require_item(
            setting.scope,
            old_item_id,
            for_update=True,
        )
        if (
            old_item.status != MemoryItemStatus.ACTIVE.value
            or old_item.version != expected_item_version
        ):
            raise MemoryConflictError("memory_item_version_conflict")
        candidate = self._require_candidate(
            setting.scope,
            candidate_id,
            for_update=True,
        )
        self._require_pending_candidate(
            candidate,
            expected_version=expected_candidate_version,
            evidence=evidence,
            memory_kind=memory_kind,
        )
        with self._session.begin_nested():
            new_item = self._new_item(
                setting=setting,
                evidence=evidence,
                memory_kind=memory_kind,
                summary=summary,
                confidence=confidence,
                salience=salience,
                valid_from=valid_from,
                valid_until=valid_until,
            )
            self._session.add(new_item)
            self._session.flush()
            self._session.add(self._new_evidence(new_item.id, evidence))
            old_item.status = MemoryItemStatus.SUPERSEDED.value
            old_item.superseded_by_id = new_item.id
            old_item.version += 1
            candidate.status = MemoryCandidateStatus.ACCEPTED.value
            candidate.reason_code = None
            candidate.decided_at = now
            candidate.version += 1
            self._invalidate_hot_briefs(setting.id, now=now)
            self._enqueue_job(
                setting.id,
                reason="memory_item_corrected",
                idempotency_key=(
                    f"memory-item:{old_item.id}:superseded:{new_item.id}:v1"
                ),
            )
            self._session.flush()
        self._session.refresh(new_item)
        return self._to_candidate(candidate), self._to_item(new_item)

    def get_item(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
    ) -> MemoryItemRecord:
        return self._to_item(self._require_item(scope, item_id))

    def get_retrievable_item(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
        now: datetime,
    ) -> MemoryItemRecord:
        try:
            self._validate_scope(scope)
        except MemoryScopeError:
            raise MemoryNotFoundError("memory_not_retrievable") from None
        setting = self._find_scope(scope)
        if setting is None or not setting.enabled:
            raise MemoryNotFoundError("memory_not_retrievable")
        row = self._session.scalar(
            select(MemoryItem).where(
                MemoryItem.id == item_id,
                *self._item_scope_predicates(scope),
            )
        )
        if row is None:
            raise MemoryNotFoundError("memory_not_retrievable")
        if (
            row.status != MemoryItemStatus.ACTIVE.value
            or row.deleted_at is not None
            or row.superseded_by_id is not None
            or is_memory_expired(
                valid_until=row.valid_until,
                pinned_at=row.pinned_at,
                now=now,
            )
        ):
            raise MemoryNotFoundError("memory_not_retrievable")
        return self._to_item(row)

    def set_item_pin(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
        expected_version: int,
        pinned: bool,
        now: datetime,
    ) -> tuple[MemoryItemRecord, bool]:
        setting = self._require_scope_row(scope)
        row = self._require_item(scope, item_id, for_update=True)
        if row.status != MemoryItemStatus.ACTIVE.value:
            raise MemoryConflictError("memory_item_version_conflict")
        if (row.pinned_at is not None) == pinned:
            return self._to_item(row), False
        if row.version != expected_version:
            raise MemoryConflictError("memory_item_version_conflict")
        if pinned and is_memory_expired(
            valid_until=row.valid_until,
            pinned_at=row.pinned_at,
            now=now,
        ):
            raise MemoryConflictError("memory_item_expired")
        row.pinned_at = now if pinned else None
        row.version += 1
        self._invalidate_hot_briefs(setting.id, now=now)
        self._enqueue_job(
            setting.id,
            reason="memory_item_pinned" if pinned else "memory_item_unpinned",
            idempotency_key=f"memory-item:{row.id}:pin:{row.version}:v1",
        )
        self._session.flush()
        return self._to_item(row), True

    def delete_item(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
        expected_version: int,
        now: datetime,
    ) -> tuple[MemoryItemRecord, bool]:
        setting = self._require_scope_row(scope)
        row = self._require_item(scope, item_id, for_update=True)
        if row.status == MemoryItemStatus.DELETED.value:
            return self._to_item(row), False
        if row.status != MemoryItemStatus.ACTIVE.value or row.version != expected_version:
            raise MemoryConflictError("memory_item_version_conflict")
        with self._session.begin_nested():
            self._mark_deleted(row, now=now)
            self._invalidate_hot_briefs(setting.id, now=now)
            self._enqueue_job(
                setting.id,
                reason="memory_item_deleted",
                idempotency_key=f"memory-item:{row.id}:deleted:v{row.version}",
            )
            self._session.flush()
        return self._to_item(row), True

    def invalidate_source(
        self,
        *,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
        now: datetime,
    ) -> tuple[MemoryItemRecord, ...]:
        setting = self._require_scope_row(scope)
        rows = list(
            self._session.scalars(
                select(MemoryItem)
                .join(
                    MemoryItemEvidence,
                    MemoryItemEvidence.memory_item_id == MemoryItem.id,
                )
                .where(
                    *self._item_scope_predicates(scope),
                    MemoryItem.status == MemoryItemStatus.ACTIVE.value,
                    MemoryItemEvidence.source_type == source_type.value,
                    MemoryItemEvidence.source_id == source_id,
                )
                .distinct()
            )
        )
        pending_candidates = list(
            self._session.scalars(
                select(MemoryCandidate).where(
                    MemoryCandidate.scope_setting_id == setting.id,
                    MemoryCandidate.source_type == source_type.value,
                    MemoryCandidate.source_id == source_id,
                    MemoryCandidate.status == MemoryCandidateStatus.PENDING.value,
                )
            )
        )
        with self._session.begin_nested():
            for candidate in pending_candidates:
                candidate.status = MemoryCandidateStatus.REJECTED.value
                candidate.reason_code = "memory_source_invalidated"
                candidate.decided_at = now
                candidate.version += 1
            for row in rows:
                self._mark_deleted(row, now=now)
                self._enqueue_job(
                    setting.id,
                    reason="memory_source_invalidated",
                    idempotency_key=(
                        f"memory-item:{row.id}:source-invalidated:v{row.version}"
                    ),
                )
            if rows:
                self._invalidate_hot_briefs(setting.id, now=now)
            self._session.flush()
        return tuple(self._to_item(row) for row in rows)

    def expire_due_items(
        self,
        *,
        scope: MemoryScope,
        now: datetime,
        limit: int,
    ) -> tuple[MemoryItemRecord, ...]:
        setting = self._require_scope_row(scope)
        due_rows = list(
            self._session.scalars(
                select(MemoryItem)
                .where(
                    *self._item_scope_predicates(scope),
                    MemoryItem.status == MemoryItemStatus.ACTIVE.value,
                    MemoryItem.pinned_at.is_(None),
                    MemoryItem.valid_until.is_not(None),
                    MemoryItem.valid_until <= now,
                )
                .order_by(MemoryItem.valid_until, MemoryItem.id)
                .limit(limit)
            )
        )
        newly_enqueued: list[MemoryItem] = []
        with self._session.begin_nested():
            for row in due_rows:
                created = self._enqueue_job(
                    setting.id,
                    reason="memory_item_expired",
                    idempotency_key=f"memory-item:{row.id}:expired:v{row.version}",
                )
                if created:
                    newly_enqueued.append(row)
            if newly_enqueued:
                self._invalidate_hot_briefs(setting.id, now=now)
            self._session.flush()
        return tuple(self._to_item(row) for row in newly_enqueued)

    def _find_scope(
        self,
        scope: MemoryScope,
        *,
        populate_existing: bool = False,
    ) -> MemoryScopeSettingModel | None:
        statement = select(MemoryScopeSettingModel).where(
            MemoryScopeSettingModel.owner_id == scope.owner_id,
            MemoryScopeSettingModel.world_id == scope.world_id,
            MemoryScopeSettingModel.subject_world_character_id
            == scope.subject_world_character_id,
        )
        if populate_existing:
            statement = statement.execution_options(populate_existing=True)
        return self._session.scalar(statement)

    def _require_scope_row(self, scope: MemoryScope) -> MemoryScopeSettingModel:
        row = self._session.scalar(
            select(MemoryScopeSettingModel)
            .where(
                MemoryScopeSettingModel.owner_id == scope.owner_id,
                MemoryScopeSettingModel.world_id == scope.world_id,
                MemoryScopeSettingModel.subject_world_character_id
                == scope.subject_world_character_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise MemoryNotFoundError("memory_scope_not_found")
        return row

    def _require_setting(self, setting: MemoryScopeSetting) -> MemoryScopeSettingModel:
        row = self._session.scalar(
            select(MemoryScopeSettingModel)
            .where(
                MemoryScopeSettingModel.id == setting.id,
                MemoryScopeSettingModel.owner_id == setting.scope.owner_id,
                MemoryScopeSettingModel.world_id == setting.scope.world_id,
                MemoryScopeSettingModel.subject_world_character_id
                == setting.scope.subject_world_character_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise MemoryNotFoundError("memory_scope_not_found")
        if row.version != setting.version or not row.enabled:
            raise MemoryConflictError("memory_scope_version_conflict")
        return row

    def _find_candidate_by_key(
        self,
        *,
        setting_id: str,
        idempotency_key: str,
    ) -> MemoryCandidate | None:
        return self._session.scalar(
            select(MemoryCandidate).where(
                MemoryCandidate.scope_setting_id == setting_id,
                MemoryCandidate.idempotency_key == idempotency_key,
            )
        )

    def _require_candidate(
        self,
        scope: MemoryScope,
        candidate_id: str,
        *,
        for_update: bool = False,
    ) -> MemoryCandidate:
        statement = (
            select(MemoryCandidate)
            .join(
                MemoryScopeSettingModel,
                MemoryScopeSettingModel.id == MemoryCandidate.scope_setting_id,
            )
            .where(
                MemoryCandidate.id == candidate_id,
                MemoryScopeSettingModel.owner_id == scope.owner_id,
                MemoryScopeSettingModel.world_id == scope.world_id,
                MemoryScopeSettingModel.subject_world_character_id
                == scope.subject_world_character_id,
            )
        )
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        row = self._session.scalar(statement)
        if row is None:
            raise MemoryNotFoundError("memory_candidate_not_found")
        return row

    def _require_pending_candidate(
        self,
        candidate: MemoryCandidate,
        *,
        expected_version: int,
        evidence: CanonicalMemoryEvidence,
        memory_kind: MemoryKindV1,
    ) -> None:
        if (
            candidate.status != MemoryCandidateStatus.PENDING.value
            or candidate.version != expected_version
        ):
            raise MemoryConflictError("memory_candidate_version_conflict")
        self._assert_candidate_replay(candidate, evidence, memory_kind)

    @staticmethod
    def _assert_candidate_replay(
        candidate: MemoryCandidate,
        evidence: CanonicalMemoryEvidence,
        memory_kind: MemoryKindV1,
    ) -> None:
        if (
            candidate.source_type != evidence.source_type.value
            or candidate.source_id != evidence.source_id
            or candidate.source_digest != evidence.source_digest
            or candidate.memory_kind_hint != memory_kind.value
        ):
            raise MemoryConflictError("memory_candidate_replay_conflict")

    def _find_item_for_candidate(
        self,
        scope: MemoryScope,
        candidate: MemoryCandidate,
    ) -> MemoryItem | None:
        return self._session.scalar(
            select(MemoryItem)
            .join(
                MemoryItemEvidence,
                MemoryItemEvidence.memory_item_id == MemoryItem.id,
            )
            .where(
                *self._item_scope_predicates(scope),
                MemoryItem.memory_kind == candidate.memory_kind_hint,
                MemoryItemEvidence.source_type == candidate.source_type,
                MemoryItemEvidence.source_id == candidate.source_id,
                MemoryItemEvidence.source_digest == candidate.source_digest,
            )
            .order_by(MemoryItem.created_at.desc(), MemoryItem.id.desc())
        )

    def _require_item(
        self,
        scope: MemoryScope,
        item_id: str,
        *,
        for_update: bool = False,
    ) -> MemoryItem:
        statement = select(MemoryItem).where(
                MemoryItem.id == item_id,
                *self._item_scope_predicates(scope),
            )
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        row = self._session.scalar(statement)
        if row is None:
            raise MemoryNotFoundError("memory_item_not_found")
        return row

    @staticmethod
    def _item_scope_predicates(scope: MemoryScope):
        return (
            MemoryItem.owner_id == scope.owner_id,
            MemoryItem.world_id == scope.world_id,
            MemoryItem.subject_world_character_id == scope.subject_world_character_id,
        )

    @staticmethod
    def _new_item(
        *,
        setting: MemoryScopeSetting,
        evidence: CanonicalMemoryEvidence,
        memory_kind: MemoryKindV1,
        summary: str,
        confidence: float,
        salience: float,
        valid_from: datetime,
        valid_until: datetime | None,
    ) -> MemoryItem:
        return MemoryItem(
            id=str(uuid4()),
            owner_id=setting.scope.owner_id,
            world_id=setting.scope.world_id,
            subject_world_character_id=setting.scope.subject_world_character_id,
            counterpart_world_character_id=evidence.counterpart_world_character_id,
            thread_id=evidence.thread_id,
            memory_kind=memory_kind.value,
            summary=summary,
            status=MemoryItemStatus.ACTIVE.value,
            confidence=confidence,
            salience=salience,
            valid_from=valid_from,
            valid_until=valid_until,
            version=1,
        )

    @staticmethod
    def _new_evidence(
        item_id: str,
        evidence: CanonicalMemoryEvidence,
    ) -> MemoryItemEvidence:
        return MemoryItemEvidence(
            id=str(uuid4()),
            memory_item_id=item_id,
            source_type=evidence.source_type.value,
            source_id=evidence.source_id,
            source_event_id=evidence.source_event_id,
            source_world_id=evidence.source_world_id,
            actor_world_character_id=evidence.actor_world_character_id,
            target_world_character_id=evidence.target_world_character_id,
            observation_id=evidence.observation_id,
            source_created_at=evidence.source_created_at,
            source_digest=evidence.source_digest,
        )

    @staticmethod
    def _mark_deleted(row: MemoryItem, *, now: datetime) -> None:
        row.status = MemoryItemStatus.DELETED.value
        row.deleted_at = now
        row.superseded_by_id = None
        row.version += 1

    def _invalidate_hot_briefs(self, setting_id: str, *, now: datetime) -> None:
        self._session.execute(
            update(MemoryHotBrief)
            .where(
                MemoryHotBrief.scope_setting_id == setting_id,
                MemoryHotBrief.status == MemoryHotBriefStatus.ACTIVE.value,
            )
            .values(
                status=MemoryHotBriefStatus.INVALIDATED.value,
                superseded_at=now,
            )
        )

    def _enqueue_job(
        self,
        setting_id: str,
        *,
        reason: str,
        idempotency_key: str,
    ) -> bool:
        existing = self._session.scalar(
            select(MemoryMaintenanceJob.id).where(
                MemoryMaintenanceJob.scope_setting_id == setting_id,
                MemoryMaintenanceJob.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return False
        self._session.add(
            MemoryMaintenanceJob(
                id=str(uuid4()),
                scope_setting_id=setting_id,
                reason=reason,
                idempotency_key=idempotency_key,
                status=MemoryJobStatus.PENDING.value,
            )
        )
        return True

    def _validate_scope(self, scope: MemoryScope) -> None:
        users = Base.metadata.tables["users"]
        worlds = Base.metadata.tables["worlds"]
        world_characters = Base.metadata.tables["world_characters"]
        owner_exists = self._session.scalar(
            select(users.c.id).where(
                users.c.id == scope.owner_id,
                users.c.deleted_at.is_(None),
            )
        )
        world_exists = self._session.scalar(
            select(worlds.c.id).where(
                worlds.c.id == scope.world_id,
                worlds.c.owner_user_id == scope.owner_id,
                worlds.c.archived_at.is_(None),
            )
        )
        subject_exists = self._session.scalar(
            select(world_characters.c.id).where(
                world_characters.c.id == scope.subject_world_character_id,
                world_characters.c.world_id == scope.world_id,
                world_characters.c.status == "active",
            )
        )
        if owner_exists is None or world_exists is None or subject_exists is None:
            raise MemoryScopeError("memory_scope_invalid")

    @staticmethod
    def _to_scope(row: MemoryScopeSettingModel) -> MemoryScopeSetting:
        return MemoryScopeSetting(
            id=row.id,
            scope=MemoryScope(
                owner_id=row.owner_id,
                world_id=row.world_id,
                subject_world_character_id=row.subject_world_character_id,
            ),
            enabled=row.enabled,
            retention_days=row.retention_days,
            provider_mode=MemoryProviderMode(row.provider_mode),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _to_candidate(row: MemoryCandidate) -> MemoryCandidateRecord:
        if row.memory_kind_hint is None:
            raise MemoryConflictError("memory_candidate_kind_missing")
        return MemoryCandidateRecord(
            id=row.id,
            scope_setting_id=row.scope_setting_id,
            source_type=MemorySourceTypeV1(row.source_type),
            source_id=row.source_id,
            source_digest=row.source_digest,
            memory_kind_hint=MemoryKindV1(row.memory_kind_hint),
            status=MemoryCandidateStatus(row.status),
            reason_code=row.reason_code,
            idempotency_key=row.idempotency_key,
            version=row.version,
            created_at=row.created_at,
            decided_at=row.decided_at,
        )

    @staticmethod
    def _to_item(row: MemoryItem) -> MemoryItemRecord:
        return MemoryItemRecord(
            id=row.id,
            scope=MemoryScope(
                owner_id=row.owner_id,
                world_id=row.world_id,
                subject_world_character_id=row.subject_world_character_id,
            ),
            counterpart_world_character_id=row.counterpart_world_character_id,
            thread_id=row.thread_id,
            memory_kind=MemoryKindV1(row.memory_kind),
            summary=row.summary,
            status=MemoryItemStatus(row.status),
            confidence=row.confidence,
            salience=row.salience,
            valid_from=row.valid_from,
            valid_until=row.valid_until,
            pinned_at=row.pinned_at,
            superseded_by_id=row.superseded_by_id,
            deleted_at=row.deleted_at,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


__all__ = ["SqlAlchemyMemoryRepository"]
