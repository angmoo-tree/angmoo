"""SQLite lease row reads and compare-and-set SQL on the caller's connection."""

from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import insert, select, update
from app.domains.runtime.constants import SCHEDULER_SINGLETON_KEY
from app.domains.runtime.contracts.lease import SchedulerLeaseState
from app.domains.runtime.models import RuntimeSchedulerLease


def current_row(connection: Any):
    table = RuntimeSchedulerLease.__table__
    row = (
        connection.execute(
            select(table).where(table.c.singleton_key == SCHEDULER_SINGLETON_KEY)
        )
        .mappings()
        .one_or_none()
    )
    return row


def insert_lease(
    connection: Any,
    *,
    installation_id: Any,
    owner_id: str,
    now: datetime,
    expires_at: datetime,
):
    table = RuntimeSchedulerLease.__table__
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


def acquire_existing(
    connection: Any,
    *,
    current_epoch: int,
    current_owner: str | None,
    next_epoch: int,
    owner_id: str,
    now: datetime,
    expires_at: datetime,
):
    table = RuntimeSchedulerLease.__table__
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
    return result


def release_current(
    connection: Any, *, owner_id: str, fencing_epoch: int, now: datetime
):
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
    return result


def cas_current(
    connection: Any,
    *,
    owner_id: str,
    fencing_epoch: int,
    now: datetime,
    values: dict[str, Any],
):
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
    return result
