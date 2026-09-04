"""Persistence and provider contracts for the existing maintenance queue's v2 lane."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domains.memory.domain.lifecycle import MemoryCandidateRecord
from app.domains.memory.domain.scope import MemoryScope, MemoryScopeSetting
from app.domains.memory.domain.selection import (
    MemorySelectionDecision,
    MemorySelectionSource,
)


@dataclass(frozen=True, slots=True)
class MemoryBatchSettings:
    version: int
    memory_enabled: bool
    ai_enabled: bool
    shutdown_enabled: bool
    schedule_enabled: bool
    local_time: str
    timezone: str
    next_due_at: datetime | None
    model_id: str | None
    profile_version: int
    pending_count: int = 0
    status: str = "disabled"
    last_code: str | None = None
    last_completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MemorySelectionBatch:
    job_id: str
    setting: MemoryScopeSetting
    candidates: tuple[MemoryCandidateRecord, ...]
    model_id: str
    scope_version: int
    settings_version: int
    profile_version: int
    attempt: int
    lease_token: str


class MemorySelectionProviderPort(Protocol):
    async def select(
        self,
        sources: tuple[MemorySelectionSource, ...],
        *,
        timeout: float,
    ) -> tuple[MemorySelectionDecision, ...]: ...


class MemoryBatchRepositoryPort(Protocol):
    def settings(self, scope: MemoryScope) -> MemoryBatchSettings: ...
    def save_settings(
        self,
        scope: MemoryScope,
        *,
        expected_version: int,
        expected_profile_version: int,
        ai_enabled: bool,
        shutdown_enabled: bool,
        schedule_enabled: bool,
        local_time: str,
        consent_version: str | None,
        model_id: str | None,
        idempotency_key: str,
        now: datetime,
    ) -> MemoryBatchSettings: ...
    def claim(
        self, *, lease_token: str, now: datetime
    ) -> MemorySelectionBatch | None: ...
    def fence(self, batch: MemorySelectionBatch, *, now: datetime) -> None: ...
    def record_call(self, batch: MemorySelectionBatch, *, now: datetime) -> None: ...
    def record_telemetry(
        self, batch: MemorySelectionBatch, *, latency_ms: int, usage: object | None
    ) -> None: ...
    def record_decision(
        self,
        batch: MemorySelectionBatch,
        candidate: MemoryCandidateRecord,
        *,
        decision: str,
        reason: str,
        item_id: str | None,
        now: datetime,
    ) -> None: ...
    def complete(self, batch: MemorySelectionBatch, *, now: datetime) -> None: ...
    def fail(
        self, batch: MemorySelectionBatch, *, code: str, now: datetime
    ) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
