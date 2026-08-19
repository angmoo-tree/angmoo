from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domains.runtime.domain.scheduler_lease import (
    SchedulerLeaseSnapshot,
    SchedulerTickPermit,
    SchedulerTickResult,
)


@runtime_checkable
class ClaimLeasePort(Protocol):
    def acquire(self, *, owner_id: str, ttl_seconds: int) -> SchedulerLeaseSnapshot: ...

    def heartbeat(
        self, *, owner_id: str, fencing_epoch: int, ttl_seconds: int
    ) -> SchedulerLeaseSnapshot: ...

    def begin_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        ttl_seconds: int,
        interval_seconds: int,
    ) -> SchedulerTickPermit: ...

    def finish_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        result: SchedulerTickResult,
        error_code: str | None = None,
    ) -> SchedulerLeaseSnapshot: ...

    def release(
        self, *, owner_id: str, fencing_epoch: int
    ) -> SchedulerLeaseSnapshot: ...

    def read(self) -> SchedulerLeaseSnapshot | None: ...


SchedulerLeaseRepository = ClaimLeasePort

__all__ = ["ClaimLeasePort", "SchedulerLeaseRepository"]
