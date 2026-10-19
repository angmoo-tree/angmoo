"""Add local connection generations without changing existing sessions/data."""
from hashlib import sha256
import json
from pathlib import Path

from .contracts import SqliteMigrationDeltaError

MUTABLE_IDENTITY_TABLES = frozenset({"auth_sessions", "local_client_connections"})


def _digest(connection, columns):
    names = ",".join(f'"{name}"' for name in columns)
    digest, count = sha256(), 0
    for row in connection.exec_driver_sql(f'SELECT {names} FROM auth_sessions ORDER BY token_hash'):
        digest.update(json.dumps(tuple(row), ensure_ascii=False, default=str).encode())
        count += 1
    return count, digest.hexdigest()


def capture_delta(connection):
    columns = tuple(row[1] for row in connection.exec_driver_sql("PRAGMA table_info(auth_sessions)"))
    if "local_client_id" in columns:
        raise SqliteMigrationDeltaError("local_client_already_present")
    return columns, _digest(connection, columns)


def upgrade(connection):
    for statement in json.loads(Path(__file__).with_name("local_client_v40_ddl.json").read_text(encoding="utf-8")):
        connection.exec_driver_sql(statement)


def verify_delta(connection, before):
    columns, digest = before
    if _digest(connection, columns) != digest:
        raise SqliteMigrationDeltaError("local_client_session_history_changed")
    if connection.exec_driver_sql("SELECT count(*) FROM auth_sessions WHERE local_client_id IS NOT NULL OR local_client_generation IS NOT NULL").scalar_one():
        raise SqliteMigrationDeltaError("local_client_migration_adopted_session")
    if connection.exec_driver_sql("SELECT count(*) FROM local_client_connections").scalar_one():
        raise SqliteMigrationDeltaError("local_client_migration_created_client")
