"""Add an empty, disposable Chat diagnostic table; preserve canonical rows."""
from sqlalchemy import Connection
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

TABLE = "chat_retrieval_diagnostics"
MUTABLE_IDENTITY_TABLES = frozenset({TABLE})


def _inventory(connection: Connection) -> frozenset:
    return frozenset(row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))


def capture_delta(connection: Connection) -> frozenset:
    before = _inventory(connection)
    if TABLE in before:
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    return before


def verify_delta(connection: Connection, before: frozenset) -> None:
    if _inventory(connection) != before | {TABLE} or connection.exec_driver_sql("SELECT count(*) FROM chat_retrieval_diagnostics").scalar_one() != 0:
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")


def upgrade(connection: Connection) -> None:
    from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata
    build_sqlite_baseline_metadata().tables[TABLE].create(connection, checkfirst=False)
