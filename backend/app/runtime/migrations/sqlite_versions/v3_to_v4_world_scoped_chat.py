"""Forward-only v3 to v4 World-scoped Chat identity migration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection

from app.domains.chat.infrastructure.world_scope_migration import (
    LEGACY_MESSAGE_THREAD_COLUMNS,
    expected_world_scope_bindings,
    rebuild_and_backfill_message_threads_v4,
)
from app.runtime.migrations.sqlite_versions.contracts import (
    SqliteMigrationDeltaError,
)


MUTABLE_IDENTITY_TABLES = frozenset({"message_threads"})


@dataclass(frozen=True)
class V3ToV4DeltaSnapshot:
    rows: dict[str, dict[str, Any]]
    expected: dict[str, tuple[str, str | None, str | None, str | None]]


def _thread_rows(connection: Connection) -> dict[str, dict[str, Any]]:
    rows = connection.exec_driver_sql(
        "SELECT * FROM message_threads ORDER BY id"
    ).mappings()
    return {str(row["id"]): dict(row) for row in rows}


def capture_v3_to_v4_delta(connection: Connection) -> V3ToV4DeltaSnapshot:
    rows = _thread_rows(connection)
    return V3ToV4DeltaSnapshot(
        rows=rows,
        expected=expected_world_scope_bindings(connection, list(rows.values())),
    )


def verify_v3_to_v4_delta(
    connection: Connection, snapshot: V3ToV4DeltaSnapshot
) -> None:
    after = _thread_rows(connection)
    if set(after) != set(snapshot.rows):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    for thread_id, before in snapshot.rows.items():
        current = after[thread_id]
        for column in LEGACY_MESSAGE_THREAD_COLUMNS:
            if current.get(column) != before.get(column):
                raise SqliteMigrationDeltaError(
                    "sqlite_migration_expected_delta_mismatch"
                )
        status, world_id, requester_id, responding_id = snapshot.expected[thread_id]
        if (
            current.get("world_scope_status") != status
            or current.get("world_id") != world_id
            or current.get("requester_world_character_id") != requester_id
            or current.get("responding_world_character_id") != responding_id
        ):
            raise SqliteMigrationDeltaError(
                "sqlite_migration_expected_delta_mismatch"
            )


def upgrade_v3_to_v4(connection: Connection) -> None:
    rebuild_and_backfill_message_threads_v4(connection)


__all__ = [
    "MUTABLE_IDENTITY_TABLES",
    "V3ToV4DeltaSnapshot",
    "capture_v3_to_v4_delta",
    "upgrade_v3_to_v4",
    "verify_v3_to_v4_delta",
]
