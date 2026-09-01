"""Forward-only v5 to v6 Chat response request lifecycle migration."""

from __future__ import annotations

from sqlalchemy import Connection

from app.domains.chat.infrastructure.sqlalchemy_models import (
    RESPONSE_REQUEST_SCHEMA_TABLES,
    create_response_request_schema,
)
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError


MUTABLE_IDENTITY_TABLES = frozenset(RESPONSE_REQUEST_SCHEMA_TABLES)


def _table_inventory(connection: Connection) -> frozenset[str]:
    return frozenset(
        str(row[0])
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    )


def capture_v5_to_v6_delta(connection: Connection) -> frozenset[str]:
    inventory = _table_inventory(connection)
    if inventory.intersection(MUTABLE_IDENTITY_TABLES):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    return inventory


def verify_v5_to_v6_delta(
    connection: Connection,
    snapshot: frozenset[str],
) -> None:
    inventory = _table_inventory(connection)
    if inventory != snapshot.union(MUTABLE_IDENTITY_TABLES):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    count = connection.exec_driver_sql(
        "SELECT count(*) FROM chat_response_requests"
    ).scalar_one()
    if int(count) != 0:
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")


def upgrade_v5_to_v6(connection: Connection) -> None:
    create_response_request_schema(connection)


__all__ = [
    "MUTABLE_IDENTITY_TABLES",
    "capture_v5_to_v6_delta",
    "upgrade_v5_to_v6",
    "verify_v5_to_v6_delta",
]
