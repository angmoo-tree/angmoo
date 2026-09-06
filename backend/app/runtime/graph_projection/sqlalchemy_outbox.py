"""SQLAlchemy outbox ports with canonical SQLite claim/finalize semantics."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.domains.worlds.service.projection_sources import list_projection_world_ids
from app.domains.relationships.repository import replay as replay_repository
from app.domains.relationships.repository import projection_state as state_repository
from app.domains.relationships.constants import LEASE_TTL_SECONDS
from app.domains.relationships.service import sqlite_projection_state
from app.domains.relationships.policies.events import _aware_utc
from app.domains.relationships.service import projection_state as graph_projection_crud
from app.domains.relationships.contracts.outbox import (OutboxFinalizeStatus, ProjectionWorkItem)
from app.domains.relationships.contracts.projection_commands import (ProjectionCommand)
from app.core.sqlite_concurrency import (
    SqliteRetryPolicy,
    run_sqlite_immediate,
)
from app.runtime.graph_projection.sqlalchemy_commands import (
    build_projection_command,
)


SessionFactory = Callable[[], Session]


class SqlAlchemyProjectionReplaySource:
    """Read deterministic replay commands from the canonical SQLite outbox."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def world_ids(self) -> tuple[str, ...]:
        with self._session_factory() as db:
            return list_projection_world_ids(db)

    def commands_for_world(
        self,
        world_id: str,
    ) -> tuple[ProjectionCommand, ...]:
        with self._session_factory() as db:
            outbox_ids = replay_repository.ordered_world_outbox_ids(db, world_id)
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
                if (row := state_repository.get_outbox(db, outbox_id)) is not None
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
        self, *, worker_id: str, now: datetime, batch_size: int
    ) -> tuple[ProjectionWorkItem, ...]:
        return sqlite_projection_state.claim(
            self._write, worker_id=worker_id, now=now, batch_size=batch_size
        )

    def load_command(self, *, outbox_id: str) -> ProjectionCommand:
        with Session(self._engine) as db:
            return build_projection_command(db, outbox_id=outbox_id)

    def finalize_success(
        self, *, outbox_id: str, worker_id: str, now: datetime
    ) -> OutboxFinalizeStatus:
        return sqlite_projection_state.finalize_success(
            self._write, outbox_id=outbox_id, worker_id=worker_id, now=now
        )

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
        return sqlite_projection_state.finalize_failure(
            self._write,
            outbox_id=outbox_id,
            worker_id=worker_id,
            now=now,
            error_class=error_class,
            terminal=terminal,
            cancelled=cancelled,
        )

    def _write(self, operation: Callable[[Any], Any]) -> Any:
        return run_sqlite_immediate(
            self._engine,
            operation,
            retry_policy=self._retry_policy,
        )


__all__ = [
    "LEASE_TTL_SECONDS",
    "SessionFactory",
    "SqlAlchemyProjectionOutbox",
    "SqliteProjectionOutbox",
]
