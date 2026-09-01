"""Bounded maintenance queue contract; no provider is connected in P8-L-F."""

from __future__ import annotations

from dataclasses import dataclass
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

    def claim(self, *, lease_token: str) -> MemoryMaintenanceWorkItem | None: ...


__all__ = ["MemoryMaintenanceQueuePort", "MemoryMaintenanceWorkItem"]
