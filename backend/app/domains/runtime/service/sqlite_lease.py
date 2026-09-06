"""SQLite lease admission, fencing decisions and transactional state workflows."""

from __future__ import annotations
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from app.domains.runtime.exceptions import (
    SchedulerLeaseHeldError,
    SchedulerLeaseLostError,
)
from app.domains.runtime.contracts.lease import (
    SchedulerLeaseSnapshot,
    SchedulerLeaseState,
    SchedulerTickPermit,
    SchedulerTickResult,
)
from app.domains.runtime.policies.lease import aware_utc, decide_tick_window
from app.domains.runtime.repository import sqlite_lease as lease_repository


class SqliteSchedulerLeaseService:
    """Durable fencing lease without PostgreSQL advisory or row locks."""

    def __init__(
        self,
        *,
        write: Callable[[Callable[[Any], Any]], Any],
        now: Callable[[], datetime],
        installation_reader: Callable[[Any], Any],
        reader: Callable[[Callable[[Any], Any]], Any],
    ) -> None:
        self._write = write
        self._now = now
        self._installation_reader = installation_reader
        self._reader = reader

    def acquire(self, *, owner_id: str, ttl_seconds: int) -> SchedulerLeaseSnapshot:
        self._validate_lease_request(owner_id=owner_id, ttl_seconds=ttl_seconds)

        def operation(connection: Any) -> SchedulerLeaseSnapshot:
            now = self._now()
            installation_id = self._installation_reader(connection)
            if installation_id is None:
                raise SchedulerLeaseLostError("local installation identity is missing")
            row = lease_repository.current_row(connection)
            expires_at = now + timedelta(seconds=ttl_seconds)
            if row is None:
                lease_repository.insert_lease(
                    connection,
                    installation_id=installation_id,
                    owner_id=owner_id,
                    now=now,
                    expires_at=expires_at,
                )
            else:
                current_owner = _optional_str(row["lease_owner_id"])
                current_expiry = _optional_datetime(row["lease_expires_at"])
                if (
                    current_owner not in {None, owner_id}
                    and current_expiry is not None
                    and (current_expiry > now)
                ):
                    raise SchedulerLeaseHeldError("scheduler lease is already held")
                current_epoch = int(row["fencing_epoch"])
                next_epoch = current_epoch + (current_owner != owner_id)
                result = lease_repository.acquire_existing(
                    connection,
                    current_epoch=current_epoch,
                    current_owner=current_owner,
                    next_epoch=next_epoch,
                    owner_id=owner_id,
                    now=now,
                    expires_at=expires_at,
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
                row, owner_id=owner_id, fencing_epoch=fencing_epoch, now=now
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
                row, owner_id=owner_id, fencing_epoch=fencing_epoch, now=now
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

    def release(self, *, owner_id: str, fencing_epoch: int) -> SchedulerLeaseSnapshot:

        def operation(connection: Any) -> SchedulerLeaseSnapshot:
            now = self._now()
            result = lease_repository.release_current(
                connection, owner_id=owner_id, fencing_epoch=fencing_epoch, now=now
            )
            if result.rowcount != 1:
                raise SchedulerLeaseLostError("scheduler lease cannot be released")
            return self._read_snapshot(connection)

        return self._write(operation)

    def _cas_current(
        self,
        connection: Any,
        *,
        owner_id: str,
        fencing_epoch: int,
        now: datetime,
        values: dict[str, Any],
    ) -> None:
        result = lease_repository.cas_current(
            connection,
            owner_id=owner_id,
            fencing_epoch=fencing_epoch,
            now=now,
            values=values,
        )
        if result.rowcount != 1:
            raise SchedulerLeaseLostError("scheduler lease CAS fence rejected")

    def _current_row(self, connection: Any, *, required: bool = True) -> Any:
        row = lease_repository.current_row(connection)
        if row is None and required:
            raise SchedulerLeaseLostError("scheduler lease is missing")
        return row

    def _read_snapshot(self, connection: Any) -> SchedulerLeaseSnapshot:
        return _snapshot(self._current_row(connection))

    @staticmethod
    def _require_current(
        row: Any, *, owner_id: str, fencing_epoch: int, now: datetime
    ) -> None:
        if not _lease_matches(
            row, owner_id=owner_id, fencing_epoch=fencing_epoch, now=now
        ):
            raise SchedulerLeaseLostError("scheduler lease is no longer current")

    @staticmethod
    def _validate_lease_request(*, owner_id: str, ttl_seconds: int) -> None:
        if not owner_id or len(owner_id) > 128:
            raise ValueError("invalid scheduler owner_id")
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")

    def read(self) -> SchedulerLeaseSnapshot | None:

        def operation(connection: Any) -> SchedulerLeaseSnapshot | None:
            row = self._current_row(connection, required=False)
            return _snapshot(row) if row is not None else None

        return self._reader(operation)


def _lease_matches(
    row: Any, *, owner_id: str, fencing_epoch: int, now: datetime
) -> bool:
    if row is None:
        return False
    expiry = _optional_datetime(row["lease_expires_at"])
    return bool(
        row["lease_owner_id"] == owner_id
        and int(row["fencing_epoch"]) == fencing_epoch
        and (row["state"] == SchedulerLeaseState.ACTIVE.value)
        and (expiry is not None)
        and (expiry > now)
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
        last_tick_result=SchedulerTickResult(str(row["last_tick_result"]))
        if row["last_tick_result"] is not None
        else None,
        next_tick_at=_optional_datetime(row["next_tick_at"]),
        last_error_code=_optional_str(row["last_error_code"]),
    )


def _optional_datetime(value: object) -> datetime | None:
    return aware_utc(value) if isinstance(value, datetime) else None


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None
