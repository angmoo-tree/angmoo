"""Storage-neutral ports for canonical recall and its private projection."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domains.memory.domain.recall import (
    CanonicalRecallQuery,
    CanonicalRecallRecord,
    MemoryRecallCandidate,
    MemoryRecallDoctor,
    MemoryRecallSearchQuery,
)
from app.domains.memory.domain.scope import MemoryScope


class MemoryRecallIndexPort(Protocol):
    def search(
        self,
        query: MemoryRecallSearchQuery,
    ) -> tuple[MemoryRecallCandidate, ...]: ...

    def doctor(self) -> MemoryRecallDoctor: ...


class CanonicalRecallRepositoryPort(Protocol):
    def memory_enabled(self, scope: MemoryScope) -> bool: ...

    def revalidate_candidates(
        self,
        *,
        scope: MemoryScope,
        candidates: tuple[MemoryRecallCandidate, ...],
        now: datetime,
    ) -> tuple[CanonicalRecallRecord, ...]: ...

    def execute_direct(
        self,
        *,
        query: CanonicalRecallQuery,
        now: datetime,
    ) -> tuple[CanonicalRecallRecord, ...]: ...


__all__ = ["CanonicalRecallRepositoryPort", "MemoryRecallIndexPort"]
