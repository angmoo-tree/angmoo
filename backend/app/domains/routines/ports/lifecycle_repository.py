from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domains.routines.contracts.lifecycle import DaypartTransitionCounts, RecoveryCounts


class LifecycleRepository(Protocol):
    def reconcile_elapsed(self, *, now: datetime) -> DaypartTransitionCounts: ...

    def recover_expired_claims(self, *, now: datetime) -> RecoveryCounts: ...


__all__ = ["LifecycleRepository"]
