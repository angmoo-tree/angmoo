"""Scheduler ownership, fencing decisions and exact transactional state changes."""

from __future__ import annotations
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from sqlalchemy.orm import Session, sessionmaker
from app.domains.runtime.constants import SCHEDULER_SINGLETON_KEY
from app.domains.runtime.contracts.lease import (
    SchedulerLeaseSnapshot,
    SchedulerLeaseState,
    SchedulerTickPermit,
    SchedulerTickResult,
)
from app.domains.runtime.exceptions import (
    SchedulerLeaseHeldError,
    SchedulerLeaseLostError,
)
from app.domains.runtime.models import RuntimeSchedulerLease
from app.domains.runtime.policies.lease import aware_utc, decide_tick_window
from app.domains.runtime.repository import scheduler_lease as lease_repository
from app.domains.runtime.repository.scheduler_lease import (
    _advisory_xact_lock,
    _database_now,
)


class SchedulerLeaseService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        installation_reader: Callable[[Session], Any],
    ) -> None:
        self._session_factory = session_factory
        self._installation_reader = installation_reader

    def acquire(self, *, owner_id: str, ttl_seconds: int) -> SchedulerLeaseSnapshot:
        with self._session_factory() as db:
            _advisory_xact_lock(db)
            now = _database_now(db)
            installation = self._installation_reader(db)
            if installation is None:
                db.rollback()
                raise SchedulerLeaseLostError("local installation identity is missing")
            row = lease_repository.locked_row(db)
            if row is None:
                row = RuntimeSchedulerLease(
                    singleton_key=SCHEDULER_SINGLETON_KEY,
                    installation_id=installation.installation_id,
                    fencing_epoch=1,
                )
                db.add(row)
            elif (
                row.lease_owner_id not in {None, owner_id}
                and row.lease_expires_at is not None
                and aware_utc(row.lease_expires_at) > now
            ):
                db.rollback()
                raise SchedulerLeaseHeldError("scheduler lease is already held")
            elif row.lease_owner_id != owner_id:
                row.fencing_epoch += 1
            row.lease_owner_id = owner_id
            row.state = SchedulerLeaseState.ACTIVE.value
            row.acquired_at = now
            row.heartbeat_at = now
            row.lease_expires_at = now + timedelta(seconds=ttl_seconds)
            row.last_observed_at = now
            row.next_tick_at = now
            row.last_error_code = None
            row.shutdown_requested_at = None
            db.commit()
            db.refresh(row)
            return _snapshot(row)

    def heartbeat(
        self, *, owner_id: str, fencing_epoch: int, ttl_seconds: int
    ) -> SchedulerLeaseSnapshot:
        with self._session_factory() as db:
            row, now = _locked_current_lease(
                db,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
            )
            previous_observed_at = row.last_observed_at
            row.last_sleep_gap_seconds = (
                max(
                    0,
                    int((now - aware_utc(previous_observed_at)).total_seconds()),
                )
                if previous_observed_at is not None
                else 0
            )
            row.heartbeat_at = now
            row.lease_expires_at = now + timedelta(seconds=ttl_seconds)
            row.last_observed_at = now
            row.state = SchedulerLeaseState.ACTIVE.value
            db.commit()
            db.refresh(row)
            return _snapshot(row)

    def begin_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        ttl_seconds: int,
        interval_seconds: int,
    ) -> SchedulerTickPermit:
        with self._session_factory() as db:
            row, now = _locked_current_lease(
                db,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
            )
            permit = decide_tick_window(
                now=now,
                interval_seconds=interval_seconds,
                last_tick_window_at=row.last_tick_window_at,
                last_observed_at=row.last_observed_at,
            )
            row.heartbeat_at = now
            row.lease_expires_at = now + timedelta(seconds=ttl_seconds)
            row.last_observed_at = now
            row.next_tick_at = permit.next_tick_at
            if permit.should_run:
                row.last_tick_window_at = permit.logical_window_at
                row.last_tick_started_at = now
                row.last_tick_finished_at = None
                row.last_tick_result = None
                row.last_error_code = None
            db.commit()
            return permit

    def finish_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        result: SchedulerTickResult,
        error_code: str | None = None,
    ) -> SchedulerLeaseSnapshot:
        with self._session_factory() as db:
            row, now = _locked_current_lease(
                db,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
            )
            row.last_tick_finished_at = now
            row.last_tick_result = result.value
            row.last_error_code = error_code
            db.commit()
            db.refresh(row)
            return _snapshot(row)

    def release(self, *, owner_id: str, fencing_epoch: int) -> SchedulerLeaseSnapshot:
        with self._session_factory() as db:
            _advisory_xact_lock(db)
            row = lease_repository.locked_row(db)
            now = _database_now(db)
            if (
                row is None
                or row.lease_owner_id != owner_id
                or row.fencing_epoch != fencing_epoch
            ):
                db.rollback()
                raise SchedulerLeaseLostError("scheduler lease cannot be released")
            row.state = SchedulerLeaseState.STOPPED.value
            row.shutdown_requested_at = now
            row.heartbeat_at = now
            row.lease_expires_at = now
            row.lease_owner_id = None
            row.next_tick_at = None
            db.commit()
            db.refresh(row)
            return _snapshot(row)

    def read(self) -> SchedulerLeaseSnapshot | None:
        with self._session_factory() as db:
            row = lease_repository.read_row(db)
            return _snapshot(row) if row is not None else None


def _locked_current_lease(
    db: Session,
    *,
    owner_id: str,
    fencing_epoch: int,
) -> tuple[RuntimeSchedulerLease, datetime]:
    _advisory_xact_lock(db)
    row = lease_repository.locked_row(db)
    now = _database_now(db)
    if not _lease_matches(row, owner_id=owner_id, fencing_epoch=fencing_epoch, now=now):
        db.rollback()
        raise SchedulerLeaseLostError("scheduler lease is no longer current")
    return row, now


def _lease_matches(
    row: RuntimeSchedulerLease | None,
    *,
    owner_id: str,
    fencing_epoch: int,
    now: datetime,
) -> bool:
    return bool(
        row is not None
        and row.lease_owner_id == owner_id
        and row.fencing_epoch == fencing_epoch
        and row.state == SchedulerLeaseState.ACTIVE.value
        and row.lease_expires_at is not None
        and aware_utc(row.lease_expires_at) > now
    )


def _snapshot(row: RuntimeSchedulerLease) -> SchedulerLeaseSnapshot:
    return SchedulerLeaseSnapshot(
        installation_id=row.installation_id,
        lease_owner_id=row.lease_owner_id,
        fencing_epoch=row.fencing_epoch,
        state=SchedulerLeaseState(row.state),
        acquired_at=row.acquired_at,
        heartbeat_at=row.heartbeat_at,
        lease_expires_at=row.lease_expires_at,
        last_tick_window_at=row.last_tick_window_at,
        last_tick_started_at=row.last_tick_started_at,
        last_tick_finished_at=row.last_tick_finished_at,
        last_tick_result=(
            SchedulerTickResult(row.last_tick_result) if row.last_tick_result else None
        ),
        next_tick_at=row.next_tick_at,
        last_error_code=row.last_error_code,
    )
