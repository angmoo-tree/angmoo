"""Bind canonical diagnostic queries to one caller-owned Session."""

from __future__ import annotations
from datetime import datetime
from functools import partial
from typing import cast
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.config import Settings, settings
from app.domains.runtime.contracts.status_queries import RuntimeStatusQueries
from app.domains.runtime.contracts.status import RuntimePersistenceProvider
from app.domains.runtime.repository import status as owned
from app.domains.runtime.service.status import RuntimeStatusService
from app.runtime.diagnostics import status_queries as foreign
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION


def create_runtime_status_reader(
    db: Session, *, config: Settings = settings, now: datetime | None = None
) -> RuntimeStatusService:
    provider = db.get_bind().dialect.name
    if provider not in {"sqlite", "postgresql"}:
        raise ValueError("runtime_status_persistence_unsupported")
    if provider == "postgresql":
        from app.runtime.persistence.postgresql_schema import VERSION

        head_revision = f"postgresql-v{VERSION}"

        def read_revision(_query: str) -> str:
            actual = db.execute(
                text("SELECT version FROM angmoo_postgresql_schema_version")
            ).scalar_one()
            return f"postgresql-v{actual}"
    else:
        head_revision = load_sqlite_manifest(SQLITE_SCHEMA_VERSION).source_revision
        read_revision = partial(owned.migration_revision, db)
    queries = RuntimeStatusQueries(
        migration_revision=read_revision,
        owner_state=partial(foreign.owner_state, db),
        registered_world_count=partial(foreign.registered_world_count, db),
        active_world_count=partial(foreign.active_world_count, db),
        active_world_character_count=partial(foreign.active_world_character_count, db),
        scheduler_state=partial(owned.scheduler_state, db),
        projection_counts=partial(foreign.projection_counts, db),
        recent_runs=partial(foreign.recent_runs, db),
        rollback=db.rollback,
    )
    return RuntimeStatusService(
        queries,
        persistence_provider=cast(RuntimePersistenceProvider, provider),
        migration_head_revision=head_revision,
        config=config,
        now=now,
    )
