"""Runtime-owned SQLite CAS implementation of the scheduler lease port."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, insert, select, update

from app.domains.identity.public import InstallationIdentity, LOCAL_INSTALLATION_KEY
from app.domains.runtime.domain.scheduler_lease import (
    SCHEDULER_SINGLETON_KEY,
    SchedulerLeaseHeldError,
    SchedulerLeaseLostError,
    SchedulerLeaseSnapshot,
    SchedulerLeaseState,
    SchedulerTickPermit,
    SchedulerTickResult,
    aware_utc,
    decide_tick_window,
)
from app.domains.runtime.infrastructure.sqlalchemy_scheduler_lease import (
    RuntimeSchedulerLease,
)
from app.core.sqlite_concurrency import (
    SqliteRetryPolicy,
    run_sqlite_immediate,
)


Clock = Callable[[], datetime]


class SqliteSchedulerLeaseRepository:
    """Durable fencing lease without PostgreSQL advisory or row locks."""

    def __init__(
        self,
        engine: Engine,
        *,
        clock: Clock | None = None,
        retry_policy: SqliteRetryPolicy | None = None,
    ) -> None:
        if engine.dialect.name != "sqlite":
            raise ValueError("SqliteSchedulerLeaseRepository requires SQLite")
        self._engine = engine
        self._clock = clock or (lambda: datetime.now(UTC))
        self._retry_policy = retry_policy

    def acquire(self, *, owner_id: str, ttl_seconds: int) -> SchedulerLeaseSnapshot:
        self._validate_lease_request(owner_id=owner_id, ttl_seconds=ttl_seconds)

        def operation(connection: Any) -> SchedulerLeaseSnapshot:
            now = self._now()
            installation_id = connection.execute(
                select(InstallationIdentity.__table__.c.installation_id).where(
                    InstallationIdentity.__table__.c.singleton_key
                    == LOCAL_INSTALLATION_KEY
                )
            ).scalar_one_or_none()
            if installation_id is None:
                raise SchedulerLeaseLostError("local installation identity is missing")
            table = RuntimeSchedulerLease.__table__
            row = connection.execute(
                select(table).where(table.c.singleton_key == SCHEDULER_SINGLETON_KEY)
            ).mappings().one_or_none()
            expires_at = now + timedelta(seconds=ttl_seconds)
            if row is None:
                connection.execute(
                    insert(table).values(
                        singleton_key=SCHEDULER_SINGLETON_KEY,
                        installation_id=str(installation_id),
                        lease_owner_id=owner_id,
                        fencing_epoch=1,
                        state=SchedulerLeaseState.ACTIVE.value,
                        acquired_at=now,
                        heartbeat_at=now,
                        lease_expires_at=expires_at,
                        last_observed_at=now,
                        last_sleep_gap_seconds=0,
                        next_tick_at=now,
                        last_error_code=None,
                        shutdown_requested_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                current_owner = _optional_str(row["lease_owner_id"])
                current_expiry = _optional_datetime(row["lease_expires_at"])
                if (
                    current_owner not in {None, owner_id}
                    and current_expiry is not None
                    and current_expiry > now
                ):
                    raise SchedulerLeaseHeldError("scheduler lease is already held")
                current_epoch = int(row["fencing_epoch"])
                next_epoch = current_epoch + (current_owner != owner_id)
                predicate = [
                    table.c.singleton_key == SCHEDULER_SINGLETON_KEY,
                    table.c.fencing_epoch == current_epoch,
                ]
                predicate.append(
                    table.c.lease_owner_id.is_(None)
                    if current_owner is None
                    else table.c.lease_owner_id == current_owner
                )
                result = connection.execute(
                    update(table)
                    .where(*predicate)
                    .values(
                        lease_owner_id=owner_id,
                        fencing_epoch=next_epoch,
                        state=SchedulerLeaseState.ACTIVE.value,
                        acquired_at=now,
                        heartbeat_at=now,
                        lease_expires_at=expires_at,
                        last_observed_at=now,
                        next_tick_at=now,
                        last_error_code=None,
                        shutdown_requested_at=None,
                        updated_at=now,
                    )
                )
                if result.rowcount != 1:
                    raise SchedulerLeaseLostError("scheduler lease CAS acquire failed")
            return self._read_snapshot(connection)

        return self._write(operation)

    def heartbeat(
        self, *, owner_id: str, fencing_epoch: int, ttl_seconds: int
    ) -> SchedulerLeaseSnapshot:
        self._validate_lease_request(owner_id=owner_id, ttl_seconds=ttl_seconds)

        def operation(connection: Any) -> SchedulerLeaseSnapshot:
            now = self._now()
            row = self._current_row(connection)
            self._require_current(
                row,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
                now=now,
            )
            previous_observed = _optional_datetime(row["last_observed_at"])
            gap = (
                max(0, int((now - previous_observed).total_seconds()))
                if previous_observed is not None
                else 0
            )
            self._cas_current(
                connection,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
                now=now,
                values={
                    "heartbeat_at": now,
                    "lease_expires_at": now + timedelta(seconds=ttl_seconds),
                    "last_observed_at": now,
                    "last_sleep_gap_seconds": gap,
                    "state": SchedulerLeaseState.ACTIVE.value,
                    "last_error_code": None,
                    "updated_at": now,
                },
            )
            return self._read_snapshot(connection)

        return self._write(operation)

    def begin_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        ttl_seconds: int,
        interval_seconds: int,
    ) -> SchedulerTickPermit:
        self._validate_lease_request(owner_id=owner_id, ttl_seconds=ttl_seconds)

        def operation(connection: Any) -> SchedulerTickPermit:
            now = self._now()
            row = self._current_row(connection)
            self._require_current(
                row,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
                now=now,
            )
            permit = decide_tick_window(
                now=now,
                interval_seconds=interval_seconds,
                last_tick_window_at=_optional_datetime(row["last_tick_window_at"]),
                last_observed_at=_optional_datetime(row["last_observed_at"]),
            )
            values: dict[str, Any] = {
                "heartbeat_at": now,
                "lease_expires_at": now + timedelta(seconds=ttl_seconds),
                "last_observed_at": now,
                "next_tick_at": permit.next_tick_at,
                "updated_at": now,
            }
            if permit.should_run:
                values.update(
                    last_tick_window_at=permit.logical_window_at,
                    last_tick_started_at=now,
                    last_tick_finished_at=None,
                    last_tick_result=None,
                    last_error_code=None,
                )
            self._cas_current(
                connection,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
                now=now,
                values=values,
            )
            return permit

        return self._write(operation)

    def finish_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        result: SchedulerTickResult,
        error_code: str | None = None,
    ) -> SchedulerLeaseSnapshot:
        def operation(connection: Any) -> SchedulerLeaseSnapshot:
            now = self._now()
            self._cas_current(
                connection,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
                now=now,
                values={
                    "last_tick_finished_at": now,
                    "last_tick_result": result.value,
                    "last_error_code": error_code,
                    "updated_at": now,
                },
            )
            return self._read_snapshot(connection)

        return self._write(operation)

    def release(
        self, *, owner_id: str, fencing_epoch: int
    ) -> SchedulerLeaseSnapshot:
        def operation(connection: Any) -> SchedulerLeaseSnapshot:
            now = self._now()
            table = RuntimeSchedulerLease.__table__
            result = connection.execute(
                update(table)
                .where(
                    table.c.singleton_key == SCHEDULER_SINGLETON_KEY,
                    table.c.lease_owner_id == owner_id,
                    table.c.fencing_epoch == fencing_epoch,
                    table.c.state == SchedulerLeaseState.ACTIVE.value,
                )
                .values(
                    state=SchedulerLeaseState.STOPPED.value,
                    shutdown_requested_at=now,
                    heartbeat_at=now,
                    lease_expires_at=now,
                    lease_owner_id=None,
                    next_tick_at=None,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                raise SchedulerLeaseLostError("scheduler lease cannot be released")
            return self._read_snapshot(connection)

        return self._write(operation)

    def read(self) -> SchedulerLeaseSnapshot | None:
        with self._engine.connect() as connection:
            row = self._current_row(connection, required=False)
            return _snapshot(row) if row is not None else None

    def _cas_current(
        self,
        connection: Any,
        *,
        owner_id: str,
        fencing_epoch: int,
        now: datetime,
        values: dict[str, Any],
    ) -> None:
        table = RuntimeSchedulerLease.__table__
        result = connection.execute(
            update(table)
            .where(
                table.c.singleton_key == SCHEDULER_SINGLETON_KEY,
                table.c.lease_owner_id == owner_id,
                table.c.fencing_epoch == fencing_epoch,
                table.c.state == SchedulerLeaseState.ACTIVE.value,
                table.c.lease_expires_at > now,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise SchedulerLeaseLostError("scheduler lease CAS fence rejected")

    def _current_row(self, connection: Any, *, required: bool = True) -> Any:
        table = RuntimeSchedulerLease.__table__
        row = connection.execute(
            select(table).where(table.c.singleton_key == SCHEDULER_SINGLETON_KEY)
        ).mappings().one_or_none()
        if row is None and required:
            raise SchedulerLeaseLostError("scheduler lease is missing")
        return row

    def _read_snapshot(self, connection: Any) -> SchedulerLeaseSnapshot:
        return _snapshot(self._current_row(connection))

    def _write(self, operation: Callable[[Any], Any]) -> Any:
        return run_sqlite_immediate(
            self._engine,
            operation,
            retry_policy=self._retry_policy,
        )

    def _now(self) -> datetime:
        return aware_utc(self._clock())

    @staticmethod
    def _require_current(
        row: Any,
        *,
        owner_id: str,
        fencing_epoch: int,
        now: datetime,
    ) -> None:
        if not _lease_matches(
            row,
            owner_id=owner_id,
            fencing_epoch=fencing_epoch,
            now=now,
        ):
            raise SchedulerLeaseLostError("scheduler lease is no longer current")

    @staticmethod
    def _validate_lease_request(*, owner_id: str, ttl_seconds: int) -> None:
        if not owner_id or len(owner_id) > 128:
            raise ValueError("invalid scheduler owner_id")
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")


def _lease_matches(
    row: Any,
    *,
    owner_id: str,
    fencing_epoch: int,
    now: datetime,
) -> bool:
    if row is None:
        return False
    expiry = _optional_datetime(row["lease_expires_at"])
    return bool(
        row["lease_owner_id"] == owner_id
        and int(row["fencing_epoch"]) == fencing_epoch
        and row["state"] == SchedulerLeaseState.ACTIVE.value
        and expiry is not None
        and expiry > now
    )


def _snapshot(row: Any) -> SchedulerLeaseSnapshot:
    return SchedulerLeaseSnapshot(
        installation_id=str(row["installation_id"]),
        lease_owner_id=_optional_str(row["lease_owner_id"]),
        fencing_epoch=int(row["fencing_epoch"]),
        state=SchedulerLeaseState(str(row["state"])),
        acquired_at=_optional_datetime(row["acquired_at"]),
        heartbeat_at=_optional_datetime(row["heartbeat_at"]),
        lease_expires_at=_optional_datetime(row["lease_expires_at"]),
        last_tick_window_at=_optional_datetime(row["last_tick_window_at"]),
        last_tick_started_at=_optional_datetime(row["last_tick_started_at"]),
        last_tick_finished_at=_optional_datetime(row["last_tick_finished_at"]),
        last_tick_result=(
            SchedulerTickResult(str(row["last_tick_result"]))
            if row["last_tick_result"] is not None
            else None
        ),
        next_tick_at=_optional_datetime(row["next_tick_at"]),
        last_error_code=_optional_str(row["last_error_code"]),
    )


def _optional_datetime(value: object) -> datetime | None:
    return aware_utc(value) if isinstance(value, datetime) else None


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


__all__ = ["Clock", "SqliteSchedulerLeaseRepository"]
