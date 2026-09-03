"""Forward-only v7 to v8 social action subjective-context migration."""

from __future__ import annotations

from sqlalchemy import Connection

from app.domains.social.infrastructure.sqlalchemy_subjective_context_models import (
    SUBJECTIVE_CONTEXT_SCHEMA_TABLES,
    create_subjective_context_schema,
)
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError


MUTABLE_IDENTITY_TABLES = frozenset(SUBJECTIVE_CONTEXT_SCHEMA_TABLES)


def _table_inventory(connection: Connection) -> frozenset[str]:
    return frozenset(
        str(row[0])
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    )


def capture_v7_to_v8_delta(connection: Connection) -> frozenset[str]:
    inventory = _table_inventory(connection)
    if inventory.intersection(MUTABLE_IDENTITY_TABLES):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    return inventory


def verify_v7_to_v8_delta(
    connection: Connection,
    snapshot: frozenset[str],
) -> None:
    inventory = _table_inventory(connection)
    if inventory != snapshot.union(MUTABLE_IDENTITY_TABLES):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    count = connection.exec_driver_sql(
        "SELECT count(*) FROM social_action_subjective_contexts"
    ).scalar_one()
    if int(count) != 0:
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")


def upgrade_v7_to_v8(connection: Connection) -> None:
    create_subjective_context_schema(connection)


__all__ = [
    "MUTABLE_IDENTITY_TABLES",
    "capture_v7_to_v8_delta",
    "upgrade_v7_to_v8",
    "verify_v7_to_v8_delta",
]
