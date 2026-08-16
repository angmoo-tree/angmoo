from __future__ import annotations

from app.domains.runtime.domain.scheduler_lease import (
    SchedulerLeaseSnapshot,
    SchedulerTickPermit,
    SchedulerTickResult,
)
from app.domains.runtime.ports.scheduler_lease_repository import (
    SchedulerLeaseRepository,
)


class SchedulerLeaseCoordinator:
    def __init__(
        self,
        repository: SchedulerLeaseRepository,
        *,
        ttl_seconds: int,
        interval_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._repository = repository
        self._ttl_seconds = ttl_seconds
        self._interval_seconds = interval_seconds

    def acquire(self, *, owner_id: str) -> SchedulerLeaseSnapshot:
        return self._repository.acquire(
            owner_id=owner_id,
            ttl_seconds=self._ttl_seconds,
        )

    def heartbeat(
        self, *, owner_id: str, fencing_epoch: int
    ) -> SchedulerLeaseSnapshot:
        return self._repository.heartbeat(
            owner_id=owner_id,
            fencing_epoch=fencing_epoch,
            ttl_seconds=self._ttl_seconds,
        )

    def begin_tick(
        self, *, owner_id: str, fencing_epoch: int
    ) -> SchedulerTickPermit:
        return self._repository.begin_tick(
            owner_id=owner_id,
            fencing_epoch=fencing_epoch,
            ttl_seconds=self._ttl_seconds,
            interval_seconds=self._interval_seconds,
        )

    def finish_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        result: SchedulerTickResult,
        error_code: str | None = None,
    ) -> SchedulerLeaseSnapshot:
        return self._repository.finish_tick(
            owner_id=owner_id,
            fencing_epoch=fencing_epoch,
            result=result,
            error_code=error_code,
        )

    def release(
        self, *, owner_id: str, fencing_epoch: int
    ) -> SchedulerLeaseSnapshot:
        return self._repository.release(
            owner_id=owner_id,
            fencing_epoch=fencing_epoch,
        )

    def read(self) -> SchedulerLeaseSnapshot | None:
        return self._repository.read()
