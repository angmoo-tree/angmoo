"""SQLAlchemy outbox ports with canonical SQLite claim/finalize semantics."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, exists, or_, select, update
from sqlalchemy.orm import Session

from app import models
from app.cruds import graph_projection as graph_projection_crud
from app.domains.relationships.ports.outbox import (
    OutboxFinalizeStatus,
    ProjectionWorkItem,
)
from app.domains.relationships.projection.commands import ProjectionCommand
from app.runtime.persistence.sqlite_concurrency import (
    SqliteRetryPolicy,
    run_sqlite_immediate,
)
from app.services.graph_projection_commands import build_projection_command


SessionFactory = Callable[[], Session]
LEASE_TTL_SECONDS = 60


class SqlAlchemyProjectionReplaySource:
    """Read deterministic replay commands from the canonical SQLite outbox."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def world_ids(self) -> tuple[str, ...]:
        with self._session_factory() as db:
            return tuple(
                str(value)
                for value in db.scalars(
                    select(models.World.id).order_by(models.World.id)
                )
            )

    def commands_for_world(
        self,
        world_id: str,
    ) -> tuple[ProjectionCommand, ...]:
        with self._session_factory() as db:
            outbox_ids = tuple(
                str(value)
                for value in db.scalars(
                    select(models.GraphProjectionOutbox.id)
                    .where(models.GraphProjectionOutbox.world_id == world_id)
                    .order_by(
                        models.GraphProjectionOutbox.created_at,
                        models.GraphProjectionOutbox.id,
                    )
                )
            )
            return tuple(
                build_projection_command(
                    db,
                    outbox_id=outbox_id,
                    replay_relationship_snapshot=True,
                )
                for outbox_id in outbox_ids
            )


class SqlAlchemyProjectionOutbox:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        batch_size: int,
    ) -> tuple[ProjectionWorkItem, ...]:
        with self._session_factory() as db:
            ids = graph_projection_crud.claim_batch(
                db,
                worker_id=worker_id,
                now=now,
                batch_size=batch_size,
            )
            items = tuple(
                ProjectionWorkItem(id=outbox_id, projection_type=row.projection_type)
                for outbox_id in ids
                if (row := db.get(models.GraphProjectionOutbox, outbox_id)) is not None
            )
            db.commit()
            return items

    def load_command(self, *, outbox_id: str) -> ProjectionCommand:
        with self._session_factory() as db:
            return build_projection_command(db, outbox_id=outbox_id)

    def finalize_success(
        self,
        *,
        outbox_id: str,
        worker_id: str,
        now: datetime,
    ) -> OutboxFinalizeStatus:
        with self._session_factory() as db:
            succeeded = graph_projection_crud.finalize_success(
                db,
                outbox_id=outbox_id,
                worker_id=worker_id,
                now=now,
            )
            db.commit()
            return "succeeded" if succeeded else "lease_lost"

    def finalize_failure(
        self,
        *,
        outbox_id: str,
        worker_id: str,
        now: datetime,
        error_class: str,
        terminal: bool,
        cancelled: bool = False,
    ) -> OutboxFinalizeStatus:
        with self._session_factory() as db:
            status = graph_projection_crud.finalize_failure(
                db,
                outbox_id=outbox_id,
                worker_id=worker_id,
                now=now,
                error_class=error_class,
                terminal=terminal,
                cancelled=cancelled,
            )
            db.commit()
            return status


class SqliteProjectionOutbox:
    """Claim/finalize outbox rows with short SQLite transactions and CAS."""

    def __init__(
        self,
        engine: Engine,
        *,
        retry_policy: SqliteRetryPolicy | None = None,
    ) -> None:
        if engine.dialect.name != "sqlite":
            raise ValueError("SqliteProjectionOutbox requires SQLite")
        self._engine = engine
        self._retry_policy = retry_policy

    def claim(
        self,
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

        return self._write(operation)

    def load_command(self, *, outbox_id: str) -> ProjectionCommand:
        with Session(self._engine) as db:
            return build_projection_command(db, outbox_id=outbox_id)

    def finalize_success(
        self,
        *,
        outbox_id: str,
        worker_id: str,
        now: datetime,
    ) -> OutboxFinalizeStatus:
        current = _aware_utc(now)

        def operation(connection: Any) -> OutboxFinalizeStatus:
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

        return self._write(operation)

    def finalize_failure(
        self,
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
            outbox = models.GraphProjectionOutbox.__table__
            row = connection.execute(
                select(outbox).where(outbox.c.id == outbox_id)
            ).mappings().one_or_none()
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

        return self._write(operation)

    def _write(self, operation: Callable[[Any], Any]) -> Any:
        return run_sqlite_immediate(
            self._engine,
            operation,
            retry_policy=self._retry_policy,
        )


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


def _row_has_active_lease(row: Any, *, worker_id: str, now: datetime) -> bool:
    expires_at = row["lease_expires_at"]
    return bool(
        row["status"] == "processing"
        and row["lease_owner"] == worker_id
        and isinstance(expires_at, datetime)
        and _aware_utc(expires_at) > now
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "LEASE_TTL_SECONDS",
    "SessionFactory",
    "SqlAlchemyProjectionOutbox",
    "SqliteProjectionOutbox",
]
