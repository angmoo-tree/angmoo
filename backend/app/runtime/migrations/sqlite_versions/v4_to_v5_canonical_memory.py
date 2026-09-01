"""Forward-only v4 to v5 canonical Memory schema migration."""

from __future__ import annotations

from sqlalchemy import Connection

from app.domains.memory.infrastructure.sqlalchemy_models import (
    MEMORY_SCHEMA_V1_TABLES,
    create_memory_schema_v1,
)
from app.runtime.migrations.sqlite_versions.contracts import (
    SqliteMigrationDeltaError,
)


MUTABLE_IDENTITY_TABLES = frozenset(MEMORY_SCHEMA_V1_TABLES)


def _table_inventory(connection: Connection) -> frozenset[str]:
    return frozenset(
        str(row[0])
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    )


def capture_v4_to_v5_delta(connection: Connection) -> frozenset[str]:
    inventory = _table_inventory(connection)
    if inventory.intersection(MUTABLE_IDENTITY_TABLES):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    return inventory


def verify_v4_to_v5_delta(
    connection: Connection,
    snapshot: frozenset[str],
) -> None:
    inventory = _table_inventory(connection)
    if inventory != snapshot.union(MUTABLE_IDENTITY_TABLES):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    for table in MUTABLE_IDENTITY_TABLES:
        quoted = '"' + table.replace('"', '""') + '"'
        if int(
            connection.exec_driver_sql(
                f"SELECT count(*) FROM {quoted}"
            ).scalar_one()
        ) != 0:
            raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")


def upgrade_v4_to_v5(connection: Connection) -> None:
    create_memory_schema_v1(connection)


__all__ = [
    "MUTABLE_IDENTITY_TABLES",
    "capture_v4_to_v5_delta",
    "upgrade_v4_to_v5",
    "verify_v4_to_v5_delta",
]
