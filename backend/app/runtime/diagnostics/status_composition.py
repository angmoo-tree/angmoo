"""Bind canonical diagnostic queries to one caller-owned Session."""

from __future__ import annotations
from datetime import datetime
from functools import partial
from sqlalchemy.orm import Session
from app.config import Settings, settings
from app.domains.runtime.contracts.status_queries import RuntimeStatusQueries
from app.domains.runtime.repository import status as owned
from app.domains.runtime.service.status import RuntimeStatusService
from app.runtime.diagnostics import status_queries as foreign


def create_runtime_status_reader(
    db: Session, *, config: Settings = settings, now: datetime | None = None
) -> RuntimeStatusService:
    queries = RuntimeStatusQueries(
        migration_revision=partial(owned.migration_revision, db),
        owner_state=partial(foreign.owner_state, db),
        registered_world_count=partial(foreign.registered_world_count, db),
        active_world_count=partial(foreign.active_world_count, db),
        active_world_character_count=partial(foreign.active_world_character_count, db),
        scheduler_state=partial(owned.scheduler_state, db),
        projection_counts=partial(foreign.projection_counts, db),
        recent_runs=partial(foreign.recent_runs, db),
        rollback=db.rollback,
    )
    return RuntimeStatusService(queries, config=config, now=now)
