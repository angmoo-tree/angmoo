"""Migration-source adapters for transition and restore tooling.

This package is also the parent of the installed-runtime LocalAppData
migration.  Keep its public exports lazy: importing
``app.runtime.migrations.local_app_data`` happens before the desktop sidecar
has configured its SQLite environment, so eagerly importing the offline
PostgreSQL adapter here would initialize the application database settings
against PostgreSQL and prevent the packaged sidecar from becoming ready.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.runtime.migrations.alembic_source import AlembicMigrationSource
    from app.runtime.migrations.postgres_to_sqlite import (
        OfflineMigrationCancelledError,
        OfflineMigrationError,
        OfflineMigrationParityError,
        OfflineMigrationSourceError,
        OfflineMigrationTargetError,
        PostgresToSqliteOfflineDryRun,
    )

__all__ = [
    "AlembicMigrationSource",
    "OFFLINE_MIGRATION_MANIFEST_NAME",
    "OFFLINE_MIGRATION_MANIFEST_VERSION",
    "OfflineMigrationCancelledError",
    "OfflineMigrationError",
    "OfflineMigrationParityError",
    "OfflineMigrationSourceError",
    "OfflineMigrationTargetError",
    "PostgresToSqliteOfflineDryRun",
]

_ALEMBIC_EXPORTS = {"AlembicMigrationSource"}
_POSTGRES_EXPORTS = set(__all__) - _ALEMBIC_EXPORTS


def __getattr__(name: str) -> Any:
    if name in _ALEMBIC_EXPORTS:
        module = import_module("app.runtime.migrations.alembic_source")
    elif name in _POSTGRES_EXPORTS:
        module = import_module("app.runtime.migrations.postgres_to_sqlite")
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(module, name)
    globals()[name] = value
    return value
