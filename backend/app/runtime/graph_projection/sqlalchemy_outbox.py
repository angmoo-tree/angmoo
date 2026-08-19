"""Current PostgreSQL/SQLAlchemy implementation of the projection outbox port."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.cruds import graph_projection as graph_projection_crud
from app.domains.relationships.ports.outbox import (
    OutboxFinalizeStatus,
    ProjectionWorkItem,
)
from app.domains.relationships.projection.commands import ProjectionCommand
from app.services.graph_projection_commands import build_projection_command


SessionFactory = Callable[[], Session]


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


__all__ = ["SessionFactory", "SqlAlchemyProjectionOutbox"]
