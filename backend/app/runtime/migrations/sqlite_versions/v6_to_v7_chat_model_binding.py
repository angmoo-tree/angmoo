"""Forward-only v6 to v7 World Chat response-model binding migration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection

from app.domains.chat.infrastructure.model_binding_migration import (
    MESSAGE_THREAD_V6_COLUMNS,
    expected_model_bindings,
    rebuild_and_backfill_message_threads_v7,
)
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError


MUTABLE_IDENTITY_TABLES = frozenset({"message_threads"})


@dataclass(frozen=True)
class V6ToV7DeltaSnapshot:
    rows: dict[str, dict[str, Any]]
    expected: dict[str, tuple[str, str]]


def _thread_rows(connection: Connection) -> dict[str, dict[str, Any]]:
    rows = connection.exec_driver_sql(
        "SELECT * FROM message_threads ORDER BY id"
    ).mappings()
    return {str(row["id"]): dict(row) for row in rows}


def capture_v6_to_v7_delta(connection: Connection) -> V6ToV7DeltaSnapshot:
    rows = _thread_rows(connection)
    return V6ToV7DeltaSnapshot(
        rows=rows,
        expected=expected_model_bindings(connection, list(rows.values())),
    )


def verify_v6_to_v7_delta(
    connection: Connection,
    snapshot: V6ToV7DeltaSnapshot,
) -> None:
    after = _thread_rows(connection)
    if set(after) != set(snapshot.rows):
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
    for thread_id, before in snapshot.rows.items():
        current = after[thread_id]
        for column in MESSAGE_THREAD_V6_COLUMNS:
            if column == "selected_model":
                continue
            if current.get(column) != before.get(column):
                raise SqliteMigrationDeltaError(
                    "sqlite_migration_expected_delta_mismatch"
                )
        expected_model, expected_binding = snapshot.expected[thread_id]
        if (
            current.get("selected_model") != expected_model
            or current.get("model_binding_mode") != expected_binding
        ):
            raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")


def upgrade_v6_to_v7(connection: Connection) -> None:
    rebuild_and_backfill_message_threads_v7(connection)


__all__ = [
    "MUTABLE_IDENTITY_TABLES",
    "V6ToV7DeltaSnapshot",
    "capture_v6_to_v7_delta",
    "upgrade_v6_to_v7",
    "verify_v6_to_v7_delta",
]
