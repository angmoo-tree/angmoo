"""Forward-only v1 to v2 World Package registry migration."""

from __future__ import annotations

from sqlalchemy import Connection

from app.runtime.migrations.sqlite_versions.contracts import (
    SqliteMigrationDeltaError,
)
from app.runtime.persistence.sqlite_schema import (
    WORLD_PACKAGE_REGISTRY_TABLES,
    build_sqlite_baseline_metadata,
)


MUTABLE_IDENTITY_TABLES = frozenset(WORLD_PACKAGE_REGISTRY_TABLES)


def capture_v1_to_v2_delta(connection: Connection) -> frozenset[str]:
    inventory = frozenset(
        str(row[0])
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    if inventory.intersection(MUTABLE_IDENTITY_TABLES):
        raise SqliteMigrationDeltaError(
            "sqlite_migration_expected_delta_mismatch"
        )
    return inventory


def verify_v1_to_v2_delta(
    connection: Connection,
    _snapshot: frozenset[str],
) -> None:
    inventory = frozenset(
        str(row[0])
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    if not MUTABLE_IDENTITY_TABLES.issubset(inventory):
        raise SqliteMigrationDeltaError(
            "sqlite_migration_expected_delta_mismatch"
        )
    for table in MUTABLE_IDENTITY_TABLES:
        quoted = '"' + table.replace('"', '""') + '"'
        if int(
            connection.exec_driver_sql(
                f"SELECT count(*) FROM {quoted}"
            ).scalar_one()
        ) != 0:
            raise SqliteMigrationDeltaError(
                "sqlite_migration_expected_delta_mismatch"
            )


def upgrade_v1_to_v2(connection: Connection) -> None:
    metadata = build_sqlite_baseline_metadata()
    metadata.create_all(
        connection,
        tables=[metadata.tables[name] for name in WORLD_PACKAGE_REGISTRY_TABLES],
        checkfirst=False,
    )


__all__ = [
    "MUTABLE_IDENTITY_TABLES",
    "capture_v1_to_v2_delta",
    "upgrade_v1_to_v2",
    "verify_v1_to_v2_delta",
]
