"""Add independent optional background without modifying any existing value."""

from __future__ import annotations

from hashlib import sha256
import json

from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError


TABLES = ("characters", "agent_creation_drafts")
MUTABLE_IDENTITY_TABLES = frozenset(TABLES)


def _digest(connection, table: str, columns: tuple[str, ...]) -> tuple[int, str]:
    digest = sha256()
    count = 0
    names = ",".join(f'"{column}"' for column in columns)
    for row in connection.exec_driver_sql(f'SELECT {names} FROM "{table}" ORDER BY id'):
        digest.update(json.dumps(tuple(row), default=str, ensure_ascii=False).encode())
        count += 1
    return count, digest.hexdigest()


def capture_delta(connection):
    result = {}
    for table in TABLES:
        columns = tuple(row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")'))
        if "character_background" in columns:
            raise SqliteMigrationDeltaError("character_background_already_present")
        result[table] = (columns, _digest(connection, table, columns))
    return result


def upgrade(connection):
    for table in TABLES:
        connection.exec_driver_sql(
            f'ALTER TABLE "{table}" ADD COLUMN character_background TEXT DEFAULT \'\' NOT NULL'
        )


def verify_delta(connection, before):
    for table, (columns, expected) in before.items():
        if _digest(connection, table, columns) != expected:
            raise SqliteMigrationDeltaError("character_background_existing_data_changed")
        if connection.exec_driver_sql(
            f'SELECT COUNT(*) FROM "{table}" WHERE character_background != \'\''
        ).scalar_one():
            raise SqliteMigrationDeltaError("character_background_default_changed")
