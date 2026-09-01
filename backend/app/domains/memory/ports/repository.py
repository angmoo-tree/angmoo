"""Canonical repository boundary for scope, candidate, and item lifecycle."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domains.memory.domain.lifecycle import (
    MemoryCandidateRecord,
    MemoryItemRecord,
)
from app.domains.memory.domain.provenance import (
    MemoryKindV1,
    MemoryProviderMode,
    MemorySourceTypeV1,
)
from app.domains.memory.domain.scope import MemoryScope, MemoryScopeSetting
from app.domains.memory.ports.source_reader import CanonicalMemoryEvidence


class MemoryRepositoryPort(Protocol):
    def validate_scope(self, scope: MemoryScope) -> None: ...

    def get_scope_setting(self, scope: MemoryScope) -> MemoryScopeSetting | None: ...

    def get_or_create_scope_setting(
        self,
        scope: MemoryScope,
    ) -> MemoryScopeSetting: ...

    def update_scope_setting(
        self,
        scope: MemoryScope,
        *,
        expected_version: int,
        enabled: bool,
        retention_days: int,
        provider_mode: MemoryProviderMode,
    ) -> MemoryScopeSetting: ...

    def upsert_candidate(
        self,
        *,
        setting: MemoryScopeSetting,
        evidence: CanonicalMemoryEvidence,
        memory_kind: MemoryKindV1,
        idempotency_key: str,
    ) -> tuple[MemoryCandidateRecord, bool]: ...

    def get_candidate(
        self,
        *,
        scope: MemoryScope,
        candidate_id: str,
    ) -> MemoryCandidateRecord: ...

    def reject_candidate(
        self,
        *,
        scope: MemoryScope,
        candidate_id: str,
        expected_version: int,
        reason_code: str,
        decided_at: datetime,
    ) -> MemoryCandidateRecord: ...

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
    ) -> tuple[MemoryCandidateRecord, MemoryItemRecord, bool]: ...

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
    ) -> tuple[MemoryCandidateRecord, MemoryItemRecord]: ...

    def get_item(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
    ) -> MemoryItemRecord: ...

    def get_retrievable_item(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
        now: datetime,
    ) -> MemoryItemRecord: ...

    def set_item_pin(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
        expected_version: int,
        pinned: bool,
        now: datetime,
    ) -> tuple[MemoryItemRecord, bool]: ...

    def delete_item(
        self,
        *,
        scope: MemoryScope,
        item_id: str,
        expected_version: int,
        now: datetime,
    ) -> tuple[MemoryItemRecord, bool]: ...

    def invalidate_source(
        self,
        *,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
        now: datetime,
    ) -> tuple[MemoryItemRecord, ...]: ...

    def expire_due_items(
        self,
        *,
        scope: MemoryScope,
        now: datetime,
        limit: int,
    ) -> tuple[MemoryItemRecord, ...]: ...


__all__ = ["MemoryRepositoryPort"]
