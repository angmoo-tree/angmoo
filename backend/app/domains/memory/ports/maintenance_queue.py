"""Bounded, leased maintenance queue contract for Memory lifecycle work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MemoryMaintenanceWorkItem:
    job_id: str
    scope_setting_id: str
    reason: str
    attempt_count: int


class MemoryMaintenanceQueuePort(Protocol):
    def enqueue(
        self,
        *,
        scope_setting_id: str,
        reason: str,
        idempotency_key: str,
    ) -> str: ...

    def claim(
        self,
        *,
        lease_token: str,
        now: datetime,
        lease_for: timedelta,
    ) -> MemoryMaintenanceWorkItem | None: ...

    def complete(
        self,
        *,
        job_id: str,
        lease_token: str,
        now: datetime,
    ) -> None: ...

    def fail(
        self,
        *,
        job_id: str,
        lease_token: str,
        error_code: str,
        retryable: bool,
        now: datetime,
    ) -> None: ...


__all__ = ["MemoryMaintenanceQueuePort", "MemoryMaintenanceWorkItem"]
