"""SQLite lease admission, retry/dead policy and transaction callback order."""
from __future__ import annotations
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from sqlalchemy import Connection
from app.domains.relationships.contracts.outbox import OutboxFinalizeStatus, ProjectionWorkItem
from app.domains.relationships.policies.events import _aware_utc
from app.domains.relationships.repository import sqlite_projection_state as projection_repository

SqliteWrite = Callable[[Callable[[Connection], Any]], Any]


def claim(
    write: SqliteWrite,
    *,
    worker_id: str,
    now: datetime,
    batch_size: int,
) -> tuple[ProjectionWorkItem, ...]:
    if not worker_id or len(worker_id) > 128:
        raise ValueError("invalid projection worker_id")
    current = _aware_utc(now)
    limit = max(1, min(batch_size, 100))

    def operation(connection: Any) -> tuple[ProjectionWorkItem, ...]:
        return projection_repository.claim(
            connection,
            worker_id=worker_id,
            current=current,
            limit=limit,
        )

    return write(operation)


def finalize_success(
    write: SqliteWrite,
    *,
    outbox_id: str,
    worker_id: str,
    now: datetime,
) -> OutboxFinalizeStatus:
    current = _aware_utc(now)

    def operation(connection: Any) -> OutboxFinalizeStatus:
        return projection_repository.finalize_success(
            connection,
            outbox_id=outbox_id,
            worker_id=worker_id,
            current=current,
        )

    return write(operation)


def finalize_failure(
    write: SqliteWrite,
    *,
    outbox_id: str,
    worker_id: str,
    now: datetime,
    error_class: str,
    terminal: bool,
    cancelled: bool = False,
) -> OutboxFinalizeStatus:
    current = _aware_utc(now)

    def operation(connection: Any) -> OutboxFinalizeStatus:
        row = projection_repository.get_failure_row(connection, outbox_id=outbox_id)
        if row is None or not _row_has_active_lease(
            row,
            worker_id=worker_id,
            now=current,
        ):
            return "lease_lost"
        attempt_count = int(row["attempt_count"])
        created_at = _aware_utc(row["created_at"])
        age = current - created_at
        if cancelled:
            status: OutboxFinalizeStatus = "cancelled"
        elif terminal or attempt_count >= 8 or age >= timedelta(hours=24):
            status = "dead"
        else:
            status = "pending"
        next_attempt_at: datetime | None = None
        completed_at: datetime | None = current
        if status == "pending":
            delays = (5, 30, 120, 600, 3600)
            index = min(max(attempt_count - 1, 0), len(delays))
            delay = delays[index] if index < len(delays) else 21_600
            next_attempt_at = current + timedelta(seconds=delay)
            completed_at = None
        return projection_repository.apply_failure_transition(
            connection,
            outbox_id=outbox_id,
            worker_id=worker_id,
            current=current,
            attempt_count=attempt_count,
            status=status,
            error_class=error_class,
            next_attempt_at=next_attempt_at,
            completed_at=completed_at,
        )

    return write(operation)


def _row_has_active_lease(row: Any, *, worker_id: str, now: datetime) -> bool:
    expires_at = row["lease_expires_at"]
    return bool(
        row["status"] == "processing"
        and row["lease_owner"] == worker_id
        and isinstance(expires_at, datetime)
        and _aware_utc(expires_at) > now
    )
