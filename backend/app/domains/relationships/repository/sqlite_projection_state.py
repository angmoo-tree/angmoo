"""Original SQLite outbox SQL and compare-and-swap writes on the supplied connection."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
from collections.abc import Mapping
from sqlalchemy import Connection, exists, or_, select, update
from app.domains.relationships import models
from app.domains.relationships.constants import LEASE_TTL_SECONDS
from app.domains.relationships.contracts.outbox import OutboxFinalizeStatus, ProjectionWorkItem


def claim(connection: Any, *, worker_id: str, current: datetime, limit: int) -> tuple[ProjectionWorkItem, ...]:
    outbox = models.GraphProjectionOutbox.__table__
    replay = models.GraphProjectionReplayRun.__table__
    active_rebuild = exists(
        select(replay.c.id).where(
            replay.c.world_id == outbox.c.world_id,
            replay.c.mode == "world_rebuild",
            replay.c.status.in_(("pending", "running")),
        )
    )
    candidates = connection.execute(
        select(outbox.c.id, outbox.c.projection_type)
        .where(
            _claimable(outbox, now=current),
            or_(
                outbox.c.next_attempt_at.is_(None),
                outbox.c.next_attempt_at <= current,
            ),
            ~active_rebuild,
        )
        .order_by(outbox.c.created_at.asc(), outbox.c.id.asc())
        .limit(limit)
    ).mappings()
    lease_expires = current + timedelta(seconds=LEASE_TTL_SECONDS)
    claimed: list[ProjectionWorkItem] = []
    for candidate in candidates:
        result = connection.execute(
            update(outbox)
            .where(
                outbox.c.id == candidate["id"],
                _claimable(outbox, now=current),
                or_(
                    outbox.c.next_attempt_at.is_(None),
                    outbox.c.next_attempt_at <= current,
                ),
            )
            .values(
                status="processing",
                lease_owner=worker_id,
                lease_expires_at=lease_expires,
                attempt_count=outbox.c.attempt_count + 1,
                updated_at=current,
            )
        )
        if result.rowcount == 1:
            claimed.append(
                ProjectionWorkItem(
                    id=str(candidate["id"]),
                    projection_type=str(candidate["projection_type"]),
                )
            )
    return tuple(claimed)


def finalize_success(connection: Any, *, outbox_id: str, worker_id: str, current: datetime) -> OutboxFinalizeStatus:
    outbox = models.GraphProjectionOutbox.__table__
    result = connection.execute(
        update(outbox)
        .where(
            outbox.c.id == outbox_id,
            _owned_active_lease(
                outbox,
                worker_id=worker_id,
                now=current,
            ),
        )
        .values(
            status="succeeded",
            completed_at=current,
            updated_at=current,
            lease_owner=None,
            lease_expires_at=None,
            next_attempt_at=None,
            last_error_class=None,
        )
    )
    return "succeeded" if result.rowcount == 1 else "lease_lost"


def get_failure_row(connection: Connection, *, outbox_id: str) -> Mapping[str, Any] | None:
    outbox = models.GraphProjectionOutbox.__table__
    row = connection.execute(
        select(outbox).where(outbox.c.id == outbox_id)
    ).mappings().one_or_none()
    return row


def apply_failure_transition(
    connection: Connection,
    *,
    outbox_id: str,
    worker_id: str,
    current: datetime,
    attempt_count: int,
    status: OutboxFinalizeStatus,
    error_class: str,
    next_attempt_at: datetime | None,
    completed_at: datetime | None,
) -> OutboxFinalizeStatus:
    outbox = models.GraphProjectionOutbox.__table__
    result = connection.execute(
        update(outbox)
        .where(
            outbox.c.id == outbox_id,
            outbox.c.status == "processing",
            outbox.c.lease_owner == worker_id,
            outbox.c.attempt_count == attempt_count,
            outbox.c.lease_expires_at > current,
        )
        .values(
            status=status,
            updated_at=current,
            lease_owner=None,
            lease_expires_at=None,
            last_error_class=error_class,
            next_attempt_at=next_attempt_at,
            completed_at=completed_at,
        )
    )
    return status if result.rowcount == 1 else "lease_lost"


def _claimable(outbox: Any, *, now: datetime) -> Any:
    return or_(
        outbox.c.status == "pending",
        (outbox.c.status == "processing") & (outbox.c.lease_expires_at < now),
    )


def _owned_active_lease(outbox: Any, *, worker_id: str, now: datetime) -> Any:
    return (
        (outbox.c.status == "processing")
        & (outbox.c.lease_owner == worker_id)
        & (outbox.c.lease_expires_at > now)
    )
