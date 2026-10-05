"""Recover the attested early v28 on an unpublished SQLite staging copy.

Final v28 already has the target shape. Neither path recaptures import
snapshots, resets World settings, nor reconstructs accepted worker inputs.
"""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import Connection

from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError


MUTABLE_IDENTITY_TABLES = frozenset({"agent_slots", "agent_runs"})
_ADDED_COLUMNS = {"agent_slots": "admission_metadata", "agent_runs": "input_snapshot"}


def _rows_digest(connection: Connection, table: str, columns: tuple[str, ...]) -> str:
    selection = ",".join(f'"{column}"' for column in columns)
    rows = sorted(
        (tuple(row) for row in connection.exec_driver_sql(f'SELECT {selection} FROM "{table}"')),
        key=repr,
    )
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def capture_delta(connection: Connection) -> dict[str, Any]:
    return {
        table: {
            "columns": columns,
            "digest": _rows_digest(connection, table, columns),
        }
        for table in _ADDED_COLUMNS
        for columns in [tuple(str(row[1]) for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")'))]
    }


def verify_delta(connection: Connection, before: dict[str, Any]) -> None:
    for table, saved in before.items():
        if _rows_digest(connection, table, saved["columns"]) != saved["digest"]:
            raise SqliteMigrationDeltaError("world_configuration_v29_admitted_input_changed")
        column = _ADDED_COLUMNS[table]
        if column not in saved["columns"] and connection.exec_driver_sql(
            f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NOT NULL'
        ).scalar_one():
            raise SqliteMigrationDeltaError("world_configuration_v29_admitted_input_recaptured")


def upgrade(connection: Connection) -> None:
    for table, column in _ADDED_COLUMNS.items():
        columns = {str(row[1]) for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")')}
        if column not in columns:
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} JSON")
    draft_fk = next(
        row for row in connection.exec_driver_sql("PRAGMA foreign_key_list(character_draft_import_origins)")
        if row[3] == "draft_id"
    )
    if draft_fk[6] == "CASCADE":
        return
    connection.exec_driver_sql(
        "CREATE TEMP TABLE world_configuration_v29_origins AS "
        "SELECT draft_id, snapshot_id FROM character_draft_import_origins"
    )
    connection.exec_driver_sql("DROP TABLE character_draft_import_origins")
    connection.exec_driver_sql("""
        CREATE TABLE character_draft_import_origins (
            draft_id VARCHAR(64) NOT NULL,
            snapshot_id VARCHAR(36) NOT NULL,
            PRIMARY KEY (draft_id),
            FOREIGN KEY(draft_id) REFERENCES agent_creation_drafts (id) ON DELETE CASCADE,
            FOREIGN KEY(snapshot_id) REFERENCES character_import_snapshots (id)
        )
    """)
    connection.exec_driver_sql(
        "INSERT INTO character_draft_import_origins (draft_id, snapshot_id) "
        "SELECT draft_id, snapshot_id FROM world_configuration_v29_origins"
    )
    connection.exec_driver_sql("DROP TABLE world_configuration_v29_origins")
