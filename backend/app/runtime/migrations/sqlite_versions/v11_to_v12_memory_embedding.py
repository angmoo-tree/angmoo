"""Add empty canonical eligibility/config tables; never backfill old memories."""
from sqlalchemy import Connection
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

TABLES = ("memory_embedding_settings", "memory_vector_eligibility")
MUTABLE_IDENTITY_TABLES = frozenset(TABLES)


def _inventory(connection):
    return frozenset(row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))


def capture_delta(connection: Connection):
    before = _inventory(connection)
    if before & MUTABLE_IDENTITY_TABLES:
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    return before


def verify_delta(connection: Connection, before):
    if _inventory(connection) != before | MUTABLE_IDENTITY_TABLES:
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    for name in TABLES:
        if connection.exec_driver_sql("SELECT count(*) FROM " + name).scalar_one() != 0:
            raise SqliteMigrationDeltaError("sqlite_migration_unexpected_memory_backfill")


def upgrade(connection: Connection):
    from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata
    metadata = build_sqlite_baseline_metadata()
    for name in TABLES:
        metadata.tables[name].create(connection, checkfirst=False)
