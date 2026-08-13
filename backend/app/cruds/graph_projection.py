from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app import models


LEASE_TTL_SECONDS = 60


@dataclass(frozen=True)
class GraphOutboxCounts:
    pending: int
    processing: int
    dead: int
    oldest_pending_at: datetime | None
    last_succeeded_at: datetime | None
    active_replay: bool
    failed_rebuild: bool


def claim_batch(
    db: Session,
    *,
    worker_id: str,
    now: datetime,
    batch_size: int,
) -> list[str]:
    active_rebuild = exists(
        select(models.GraphProjectionReplayRun.id).where(
            models.GraphProjectionReplayRun.world_id
            == models.GraphProjectionOutbox.world_id,
            models.GraphProjectionReplayRun.mode == "world_rebuild",
            models.GraphProjectionReplayRun.status.in_(("pending", "running")),
        )
    )
    rows = list(
        db.scalars(
            select(models.GraphProjectionOutbox)
            .where(
                or_(
                    models.GraphProjectionOutbox.status == "pending",
                    (
                        (models.GraphProjectionOutbox.status == "processing")
                        & (
                            models.GraphProjectionOutbox.lease_expires_at
                            < now
                        )
                    ),
                ),
                or_(
                    models.GraphProjectionOutbox.next_attempt_at.is_(None),
                    models.GraphProjectionOutbox.next_attempt_at <= now,
                ),
                ~active_rebuild,
            )
            .order_by(
                models.GraphProjectionOutbox.created_at.asc(),
                models.GraphProjectionOutbox.id.asc(),
            )
            .with_for_update(skip_locked=True)
            .limit(max(1, min(batch_size, 100)))
        )
    )
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
    row = db.get(models.GraphProjectionOutbox, outbox_id)
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
    row = db.get(models.GraphProjectionOutbox, outbox_id)
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


def world_counts(db: Session, *, world_id: str) -> GraphOutboxCounts:
    counts = dict(
        db.execute(
            select(
                models.GraphProjectionOutbox.status,
                func.count(models.GraphProjectionOutbox.id),
            )
            .where(models.GraphProjectionOutbox.world_id == world_id)
            .group_by(models.GraphProjectionOutbox.status)
        ).all()
    )
    oldest_pending_at = db.scalar(
        select(func.min(models.GraphProjectionOutbox.created_at)).where(
            models.GraphProjectionOutbox.world_id == world_id,
            models.GraphProjectionOutbox.status.in_(("pending", "processing")),
        )
    )
    last_succeeded_at = db.scalar(
        select(func.max(models.GraphProjectionOutbox.completed_at)).where(
            models.GraphProjectionOutbox.world_id == world_id,
            models.GraphProjectionOutbox.status == "succeeded",
        )
    )
    active_replay = db.scalar(
        select(models.GraphProjectionReplayRun.id).where(
            models.GraphProjectionReplayRun.world_id == world_id,
            models.GraphProjectionReplayRun.mode == "world_rebuild",
            models.GraphProjectionReplayRun.status.in_(("pending", "running")),
        )
    ) is not None
    latest_rebuild_status = db.scalar(
        select(models.GraphProjectionReplayRun.status)
        .where(
            models.GraphProjectionReplayRun.world_id == world_id,
            models.GraphProjectionReplayRun.mode == "world_rebuild",
        )
        .order_by(
            models.GraphProjectionReplayRun.created_at.desc(),
            models.GraphProjectionReplayRun.id.desc(),
        )
        .limit(1)
    )
    return GraphOutboxCounts(
        pending=int(counts.get("pending", 0)),
        processing=int(counts.get("processing", 0)),
        dead=int(counts.get("dead", 0)),
        oldest_pending_at=oldest_pending_at,
        last_succeeded_at=last_succeeded_at,
        active_replay=active_replay,
        failed_rebuild=latest_rebuild_status == "failed",
    )
