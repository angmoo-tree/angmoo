"""Add empty episode/thought tables; preserve legacy evidence and declarations."""

from sqlalchemy import Connection
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError
from app.runtime.persistence.sqlite_schema import EPISODE_V13_TABLES

MUTABLE_IDENTITY_TABLES = frozenset(EPISODE_V13_TABLES)


def _inventory(connection: Connection) -> frozenset[str]:
    return frozenset(row[0] for row in connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ))


def capture_delta(connection: Connection) -> frozenset[str]:
    before = _inventory(connection)
    if before & MUTABLE_IDENTITY_TABLES:
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    return before


def verify_delta(connection: Connection, before: frozenset[str]) -> None:
    if _inventory(connection) != before | MUTABLE_IDENTITY_TABLES:
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    for name in EPISODE_V13_TABLES:
        if connection.exec_driver_sql("SELECT count(*) FROM " + name).scalar_one():
            raise SqliteMigrationDeltaError("sqlite_migration_unexpected_memory_backfill")


def upgrade(connection: Connection) -> None:
    from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata
    metadata = build_sqlite_baseline_metadata()
    metadata.create_all(connection, tables=[metadata.tables[name] for name in EPISODE_V13_TABLES], checkfirst=False)
