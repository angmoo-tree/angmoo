"""Original SQLAlchemy outbox lease transitions in the caller transaction."""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
from sqlalchemy.orm import Session
from app.domains.relationships.constants import LEASE_TTL_SECONDS
from app.domains.relationships.repository import projection_state as projection_repository


def claim_batch(
    db: Session,
    *,
    worker_id: str,
    now: datetime,
    batch_size: int,
) -> list[str]:
    rows = projection_repository.claimable_rows(db, now=now, batch_size=batch_size)
    lease_expires_at = now + timedelta(seconds=LEASE_TTL_SECONDS)
    for row in rows:
        row.status = "processing"
        row.lease_owner = worker_id
        row.lease_expires_at = lease_expires_at
        row.attempt_count += 1
        row.updated_at = now
    db.flush()
    return [row.id for row in rows]


def finalize_success(
    db: Session,
    *,
    outbox_id: str,
    worker_id: str,
    now: datetime,
) -> bool:
    row = projection_repository.get_outbox(db, outbox_id)
    if row is None or row.status != "processing" or row.lease_owner != worker_id:
        return False
    row.status = "succeeded"
    row.completed_at = now
    row.updated_at = now
    row.lease_owner = None
    row.lease_expires_at = None
    row.next_attempt_at = None
    row.last_error_class = None
    return True


def finalize_failure(
    db: Session,
    *,
    outbox_id: str,
    worker_id: str,
    now: datetime,
    error_class: str,
    terminal: bool,
    cancelled: bool = False,
) -> str:
    row = projection_repository.get_outbox(db, outbox_id)
    if row is None or row.status != "processing" or row.lease_owner != worker_id:
        return "lease_lost"
    age = now - (
        row.created_at.replace(tzinfo=UTC)
        if row.created_at.tzinfo is None
        else row.created_at.astimezone(UTC)
    )
    if cancelled:
        status = "cancelled"
    elif terminal or row.attempt_count >= 8 or age >= timedelta(hours=24):
        status = "dead"
    else:
        status = "pending"
    row.status = status
    row.updated_at = now
    row.lease_owner = None
    row.lease_expires_at = None
    row.last_error_class = error_class
    if status == "pending":
        delays = (5, 30, 120, 600, 3600)
        index = min(max(row.attempt_count - 1, 0), len(delays))
        delay = delays[index] if index < len(delays) else 21600
        row.next_attempt_at = now + timedelta(seconds=delay)
        row.completed_at = None
    else:
        row.next_attempt_at = None
        row.completed_at = now
    return status
