"""Persistence and provider contracts for the existing maintenance queue's v2 lane."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domains.memory.contracts.items import MemoryCandidateRecord
from app.domains.memory.contracts.scope import MemoryScope, MemoryScopeSetting
from app.domains.memory.policies.selection_output import (
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
    thinking_level: str = "high"
    pending_count: int = 0
    run_saved_count: int | None = None
    run_pending_count: int | None = None
    status: str = "disabled"
    last_code: str | None = None
    last_completed_at: datetime | None = None
    stored_count: int = 0
    storage_limit: int = 100_000
    capacity_blocked: bool = False
    can_run: bool = False
    retryable: bool = False


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
    thinking_level: str = "high"
    policy_version: str = "memory-batch.v2"
    cutoff_sequence: int = 0


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
        thinking_level: str = "high",
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
    def defer_capacity(self, batch: MemorySelectionBatch, *, now: datetime) -> None: ...
    def fail(
        self, batch: MemorySelectionBatch, *, code: str, now: datetime,
        latency_ms: int | None = None, usage: object | None = None,
    ) -> bool: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
