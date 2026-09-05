from __future__ import annotations

from dataclasses import dataclass

from app.domains.routines.contracts.lifecycle import DaypartTransitionCounts, RecoveryCounts
from app.domains.routines.contracts.clock import Clock
from app.domains.routines.ports.lifecycle_repository import LifecycleRepository


@dataclass(frozen=True)
class ReconcileElapsedRoutines:
    repository: LifecycleRepository
    clock: Clock

    def __call__(self) -> DaypartTransitionCounts:
        return self.repository.reconcile_elapsed(now=self.clock.now_utc())


@dataclass(frozen=True)
class RecoverExpiredRoutineClaims:
    repository: LifecycleRepository
    clock: Clock

    def __call__(self) -> RecoveryCounts:
        return self.repository.recover_expired_claims(now=self.clock.now_utc())


__all__ = ["ReconcileElapsedRoutines", "RecoverExpiredRoutineClaims"]
