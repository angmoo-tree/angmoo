"""Forward-only additive Memory batch settings/admission/audit migration."""

from sqlalchemy import Connection

from app.domains.memory.infrastructure.batch_models import (
    MEMORY_BATCH_TABLES,
    create_memory_batch_schema,
)
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError


MUTABLE_IDENTITY_TABLES = frozenset(MEMORY_BATCH_TABLES)


def _tables(connection: Connection) -> frozenset[str]:
    return frozenset(
        str(row[0])
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    )


def capture_v8_to_v9_delta(connection: Connection) -> frozenset[str]:
    snapshot = _tables(connection)
    if snapshot.intersection(MUTABLE_IDENTITY_TABLES):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    return snapshot


def verify_v8_to_v9_delta(connection: Connection, snapshot: frozenset[str]) -> None:
    if _tables(connection) != snapshot.union(MUTABLE_IDENTITY_TABLES):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    for name in MEMORY_BATCH_TABLES:
        if (
            connection.exec_driver_sql(f'SELECT count(*) FROM "{name}"').scalar_one()
            != 0
        ):
            raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")


def upgrade_v8_to_v9(connection: Connection) -> None:
    create_memory_batch_schema(connection)
