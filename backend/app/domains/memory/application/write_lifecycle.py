"""Provider-free Memory candidate, acceptance, and lifecycle use cases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domains.memory.domain.errors import MemoryConflictError
from app.domains.memory.domain.lifecycle import (
    MemoryItemRecord,
    MemoryWriteOutcome,
    MemoryWriteResult,
    as_utc,
    memory_candidate_idempotency_key,
    normalize_memory_source_id,
    normalize_memory_summary,
    validate_source_digest,
    validate_source_kind,
)
from app.domains.memory.domain.policies import validate_memory_item_shape
from app.domains.memory.domain.provenance import MemoryKindV1, MemorySourceTypeV1
from app.domains.memory.domain.scope import MemoryScope, MemoryScopeSetting
from app.domains.memory.ports.repository import MemoryRepositoryPort
from app.domains.memory.ports.source_reader import (
    CanonicalMemoryEvidence,
    MemorySourceEvidenceReaderPort,
)


class MemoryWriteLifecycleService:
    """Own deterministic foreground writes; no provider port is accepted."""

    def __init__(
        self,
        repository: MemoryRepositoryPort,
        source_reader: MemorySourceEvidenceReaderPort,
    ) -> None:
        self._repository = repository
        self._source_reader = source_reader

    def propose_candidate(
        self,
        *,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
        memory_kind: MemoryKindV1,
    ) -> MemoryWriteResult:
        validate_source_kind(source_type=source_type, memory_kind=memory_kind)
        normalized_source_id = normalize_memory_source_id(source_id)
        self._repository.validate_scope(scope)
        setting = self._repository.get_scope_setting(scope)
        if setting is None or not setting.enabled:
            return self._blocked("memory_opt_out")

        evidence = self._source_reader.read_evidence(
            scope=scope,
            source_type=source_type,
            source_id=normalized_source_id,
        )
        blocked_code = self._evidence_blocked_code(
            scope=scope,
            source_type=source_type,
            source_id=normalized_source_id,
            evidence=evidence,
        )
        if blocked_code is not None:
            return self._blocked(blocked_code)
        assert evidence is not None
        self._validate_shape(memory_kind=memory_kind, evidence=evidence)

        candidate, created = self._repository.upsert_candidate(
            setting=setting,
            evidence=evidence,
            memory_kind=memory_kind,
            idempotency_key=memory_candidate_idempotency_key(
                scope=scope,
                source_type=source_type,
                source_id=normalized_source_id,
                memory_kind=memory_kind,
            ),
        )
        return MemoryWriteResult(
            outcome=(
                MemoryWriteOutcome.CREATED if created else MemoryWriteOutcome.REUSED
            ),
            code="memory_candidate_created" if created else "memory_candidate_reused",
            candidate=candidate,
            writes=("memory_candidate",) if created else (),
        )

    def accept_candidate(
        self,
        *,
        scope: MemoryScope,
        candidate_id: str,
        expected_candidate_version: int,
        expected_scope_version: int,
        summary_proposal: str | None = None,
        enqueue_maintenance: bool = True,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        accepted_at = as_utc(now or datetime.now(UTC))
        setting = self._require_enabled_setting(
            scope=scope,
            expected_version=expected_scope_version,
        )
        candidate = self._repository.get_candidate(
            scope=scope,
            candidate_id=candidate_id,
        )
        evidence = self._source_reader.read_evidence(
            scope=scope,
            source_type=candidate.source_type,
            source_id=candidate.source_id,
        )
        blocked_code = self._evidence_blocked_code(
            scope=scope,
            source_type=candidate.source_type,
            source_id=candidate.source_id,
            evidence=evidence,
        )
        if blocked_code is not None:
            return self.reject_candidate(
                scope=scope,
                candidate_id=candidate_id,
                expected_candidate_version=expected_candidate_version,
                reason_code=blocked_code,
                now=accepted_at,
            )
        assert evidence is not None
        if validate_source_digest(evidence.source_digest) != candidate.source_digest:
            raise MemoryConflictError("memory_source_digest_conflict")
        self._validate_shape(
            memory_kind=candidate.memory_kind_hint,
            evidence=evidence,
        )
        confidence, salience = _deterministic_scores(candidate.memory_kind_hint)
        stored_candidate, item, created = self._repository.accept_candidate(
            setting=setting,
            candidate_id=candidate_id,
            expected_candidate_version=expected_candidate_version,
            evidence=evidence,
            memory_kind=candidate.memory_kind_hint,
            summary=normalize_memory_summary(
                evidence.deterministic_summary
                if summary_proposal is None
                else summary_proposal
            ),
            confidence=confidence,
            salience=salience,
            valid_from=as_utc(evidence.source_created_at),
            valid_until=accepted_at + timedelta(days=setting.retention_days),
            now=accepted_at,
            enqueue_maintenance=enqueue_maintenance,
        )
        return MemoryWriteResult(
            outcome=(
                MemoryWriteOutcome.ACCEPTED if created else MemoryWriteOutcome.REUSED
            ),
            code="memory_item_accepted" if created else "memory_item_reused",
            candidate=stored_candidate,
            item=item,
            writes=(
                (
                    "memory_candidate",
                    "memory_item",
                    "memory_item_evidence",
                    *(("maintenance_job",) if enqueue_maintenance else ()),
                )
                if created
                else ()
            ),
        )

    def reject_candidate(
        self,
        *,
        scope: MemoryScope,
        candidate_id: str,
        expected_candidate_version: int,
        reason_code: str,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        candidate = self._repository.reject_candidate(
            scope=scope,
            candidate_id=candidate_id,
            expected_version=expected_candidate_version,
            reason_code=_reason_code(reason_code),
            decided_at=as_utc(now or datetime.now(UTC)),
        )
        return MemoryWriteResult(
            outcome=MemoryWriteOutcome.REJECTED,
            code=reason_code,
            candidate=candidate,
            writes=("memory_candidate",),
        )

    def correct_item(
        self,
        *,
        scope: MemoryScope,
        old_item_id: str,
        expected_item_version: int,
        candidate_id: str,
        expected_candidate_version: int,
        expected_scope_version: int,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        corrected_at = as_utc(now or datetime.now(UTC))
        setting = self._require_enabled_setting(
            scope=scope,
            expected_version=expected_scope_version,
        )
        candidate = self._repository.get_candidate(
            scope=scope,
            candidate_id=candidate_id,
        )
        evidence = self._source_reader.read_evidence(
            scope=scope,
            source_type=candidate.source_type,
            source_id=candidate.source_id,
        )
        blocked_code = self._evidence_blocked_code(
            scope=scope,
            source_type=candidate.source_type,
            source_id=candidate.source_id,
            evidence=evidence,
        )
        if blocked_code is not None:
            return self.reject_candidate(
                scope=scope,
                candidate_id=candidate_id,
                expected_candidate_version=expected_candidate_version,
                reason_code=blocked_code,
                now=corrected_at,
            )
        assert evidence is not None
        if validate_source_digest(evidence.source_digest) != candidate.source_digest:
            raise MemoryConflictError("memory_source_digest_conflict")
        self._validate_shape(
            memory_kind=candidate.memory_kind_hint,
            evidence=evidence,
        )
        confidence, salience = _deterministic_scores(candidate.memory_kind_hint)
        stored_candidate, new_item = self._repository.correct_item(
            setting=setting,
            old_item_id=old_item_id,
            expected_item_version=expected_item_version,
            candidate_id=candidate_id,
            expected_candidate_version=expected_candidate_version,
            evidence=evidence,
            memory_kind=candidate.memory_kind_hint,
            summary=normalize_memory_summary(evidence.deterministic_summary),
            confidence=confidence,
            salience=salience,
            valid_from=as_utc(evidence.source_created_at),
            valid_until=corrected_at + timedelta(days=setting.retention_days),
            now=corrected_at,
        )
        return MemoryWriteResult(
            outcome=MemoryWriteOutcome.UPDATED,
            code="memory_item_corrected",
            candidate=stored_candidate,
            item=new_item,
            writes=(
                "memory_candidate",
                "memory_item",
                "memory_item_evidence",
                "maintenance_job",
            ),
        )

    def set_pin(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
        expected_version: int,
        pinned: bool,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        item, changed = self._repository.set_item_pin(
            scope=scope,
            item_id=item_id,
            expected_version=expected_version,
            pinned=pinned,
            now=as_utc(now or datetime.now(UTC)),
        )
        return MemoryWriteResult(
            outcome=(MemoryWriteOutcome.UPDATED if changed else MemoryWriteOutcome.REUSED),
            code=(
                ("memory_item_pinned" if pinned else "memory_item_unpinned")
                if changed
                else "memory_item_pin_reused"
            ),
            item=item,
            writes=("memory_item", "maintenance_job") if changed else (),
        )

    def delete_item(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> MemoryWriteResult:
        item, changed = self._repository.delete_item(
            scope=scope,
            item_id=item_id,
            expected_version=expected_version,
            now=as_utc(now or datetime.now(UTC)),
        )
        return MemoryWriteResult(
            outcome=(MemoryWriteOutcome.DELETED if changed else MemoryWriteOutcome.REUSED),
            code="memory_item_deleted" if changed else "memory_item_delete_reused",
            item=item,
            writes=("memory_item", "maintenance_job") if changed else (),
        )

    def invalidate_source(
        self,
        *,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
        now: datetime | None = None,
    ) -> tuple[MemoryWriteResult, ...]:
        normalized_source_id = normalize_memory_source_id(source_id)
        items = self._repository.invalidate_source(
            scope=scope,
            source_type=source_type,
            source_id=normalized_source_id,
            now=as_utc(now or datetime.now(UTC)),
        )
        return tuple(
            MemoryWriteResult(
                outcome=MemoryWriteOutcome.DELETED,
                code="memory_source_invalidated",
                item=item,
                writes=("memory_item", "maintenance_job"),
            )
            for item in items
        )

    def expire_due(
        self,
        *,
        scope: MemoryScope,
        now: datetime | None = None,
        limit: int = 100,
    ) -> tuple[MemoryWriteResult, ...]:
        if limit < 1 or limit > 500:
            raise MemoryConflictError("memory_expiry_limit_invalid")
        items = self._repository.expire_due_items(
            scope=scope,
            now=as_utc(now or datetime.now(UTC)),
            limit=limit,
        )
        return tuple(
            MemoryWriteResult(
                outcome=MemoryWriteOutcome.UPDATED,
                code="memory_item_expired",
                item=item,
                writes=("maintenance_job",),
            )
            for item in items
        )

    def get_retrievable_item(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
        now: datetime | None = None,
    ) -> MemoryItemRecord:
        return self._repository.get_retrievable_item(
            scope=scope,
            item_id=item_id,
            now=as_utc(now or datetime.now(UTC)),
        )

    def _require_enabled_setting(
        self,
        *,
        scope: MemoryScope,
        expected_version: int,
    ) -> MemoryScopeSetting:
        self._repository.validate_scope(scope)
        setting = self._repository.get_scope_setting(scope)
        if setting is None or not setting.enabled:
            raise MemoryConflictError("memory_opt_out")
        if setting.version != expected_version:
            raise MemoryConflictError("memory_scope_version_conflict")
        return setting

    @staticmethod
    def _evidence_blocked_code(
        *,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
        evidence: CanonicalMemoryEvidence | None,
    ) -> str | None:
        return memory_evidence_blocked_code(
            scope=scope,
            source_type=source_type,
            source_id=source_id,
            evidence=evidence,
        )

    @staticmethod
    def _validate_shape(
        *,
        memory_kind: MemoryKindV1,
        evidence: CanonicalMemoryEvidence,
    ) -> None:
        validate_memory_item_shape(
            kind=memory_kind,
            counterpart_world_character_id=evidence.counterpart_world_character_id,
            thread_id=evidence.thread_id,
        )

    @staticmethod
    def _blocked(code: str) -> MemoryWriteResult:
        return MemoryWriteResult(
            outcome=MemoryWriteOutcome.REJECTED,
            code=code,
            writes=(),
            provider_call_count=0,
        )


def _deterministic_scores(kind: MemoryKindV1) -> tuple[float, float]:
    return {
        MemoryKindV1.OWNER_PREFERENCE: (1.0, 1.0),
        MemoryKindV1.AUTOBIOGRAPHICAL_EVENT: (0.9, 0.65),
        MemoryKindV1.DIRECTIONAL_RELATIONSHIP: (0.95, 0.8),
        MemoryKindV1.THREAD_SUMMARY: (0.9, 0.6),
        MemoryKindV1.ACCEPTED_JOINT_COMMITMENT: (1.0, 0.9),
    }[kind]


def memory_evidence_blocked_code(
    *,
    scope: MemoryScope,
    source_type: MemorySourceTypeV1,
    source_id: str,
    evidence: CanonicalMemoryEvidence | None,
) -> str | None:
    """Revalidate canonical evidence before any provider or item write."""

    if evidence is None:
        return "memory_source_not_found"
    if evidence.source_type is not source_type or evidence.source_id != source_id:
        return "memory_source_identity_mismatch"
    if evidence.source_world_id != scope.world_id:
        return "memory_world_mismatch"
    if not evidence.successful:
        return "memory_source_not_successful"
    if not evidence.visible:
        return "memory_source_not_visible"
    if not evidence.membership_active:
        return "memory_membership_inactive"
    if evidence.blocked:
        return "memory_blocked"
    if not evidence.observed_by_subject:
        return "memory_unobserved"
    validate_source_digest(evidence.source_digest)
    normalize_memory_summary(evidence.deterministic_summary)
    return None


def _reason_code(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 80:
        raise MemoryConflictError("memory_reason_code_invalid")
    return normalized


__all__ = ["MemoryWriteLifecycleService", "memory_evidence_blocked_code"]
