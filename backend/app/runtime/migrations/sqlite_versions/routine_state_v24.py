"""Add beat version with exhaustive preservation of the existing row values."""
from hashlib import sha256
import json
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

MUTABLE_IDENTITY_TABLES = frozenset({"activity_beats"})


def _digest(connection, columns):
    names = ",".join(f'"{name}"' for name in columns)
    digest = sha256()
    count = 0
    for row in connection.exec_driver_sql(f'SELECT {names} FROM activity_beats ORDER BY id'):
        digest.update(json.dumps(tuple(row), ensure_ascii=False, default=str).encode())
        count += 1
    return count, digest.hexdigest()


def capture_delta(connection):
    columns = tuple(row[1] for row in connection.exec_driver_sql("PRAGMA table_info(activity_beats)"))
    if "state_schema_version" in columns:
        raise SqliteMigrationDeltaError("routine_state_version_already_present")
    return columns, _digest(connection, columns)


def upgrade(connection):
    connection.exec_driver_sql("ALTER TABLE activity_beats ADD COLUMN state_schema_version INTEGER DEFAULT '1' NOT NULL")


def verify_delta(connection, before):
    columns, digest = before
    if _digest(connection, columns) != digest or connection.exec_driver_sql("SELECT COUNT(*) FROM activity_beats WHERE state_schema_version != 1").scalar_one():
        raise SqliteMigrationDeltaError("routine_state_history_changed")
