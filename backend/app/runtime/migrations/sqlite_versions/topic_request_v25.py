"""Only add nullable request metadata; old rows retain all bytes and legacy policy."""
from hashlib import sha256
import json
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

TABLE = "social_recommendation_preparations"
MUTABLE_IDENTITY_TABLES = frozenset({TABLE})


def _digest(connection, columns):
    names = ",".join(f'"{name}"' for name in columns)
    digest, count = sha256(), 0
    for row in connection.exec_driver_sql(f'SELECT {names} FROM {TABLE} ORDER BY id'):
        digest.update(json.dumps(tuple(row), ensure_ascii=False, default=str).encode())
        count += 1
    return count, digest.hexdigest()


def capture_delta(connection):
    columns = tuple(row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({TABLE})"))
    if "request_snapshot" in columns:
        raise SqliteMigrationDeltaError("topic_request_snapshot_already_present")
    return columns, _digest(connection, columns)


def upgrade(connection):
    connection.exec_driver_sql(f"ALTER TABLE {TABLE} ADD COLUMN request_snapshot JSON")


def verify_delta(connection, before):
    columns, digest = before
    if _digest(connection, columns) != digest or connection.exec_driver_sql(
        f"SELECT COUNT(*) FROM {TABLE} WHERE request_snapshot IS NOT NULL").scalar_one():
        raise SqliteMigrationDeltaError("topic_request_history_changed")
