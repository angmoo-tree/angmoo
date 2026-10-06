"""Frozen additive environment upgrade; never rewrite user content or secrets."""
import hashlib
import json
from pathlib import Path

from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError
from app.runtime.persistence.sqlite_environment_schema import ADDED_COLUMNS, NEW_TABLES
MUTABLE_IDENTITY_TABLES = NEW_TABLES | ADDED_COLUMNS.keys()


def _digest(connection, table, columns):
    names = ",".join(f'"{name}"' for name in columns)
    rows = sorted([tuple(row) for row in connection.exec_driver_sql(f'SELECT {names} FROM "{table}"')], key=repr)
    return hashlib.sha256(json.dumps(rows, default=str, ensure_ascii=False).encode()).hexdigest()


def capture_delta(connection):
    result = {}
    for table in ADDED_COLUMNS:
        columns = tuple(row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")'))
        result[table] = {"columns": columns, "digest": _digest(connection, table, columns)}
    return result


def verify_delta(connection, before):
    for table, data in before.items():
        if _digest(connection, table, data["columns"]) != data["digest"]:
            raise SqliteMigrationDeltaError("environment_original_changed")
    if connection.exec_driver_sql("SELECT count(*) FROM users WHERE ui_language IS NOT NULL OR ui_preference_revision != 0").scalar_one():
        raise SqliteMigrationDeltaError("environment_migration_assigned_preference")
    for name in NEW_TABLES:
        if connection.exec_driver_sql(f'SELECT count(*) FROM "{name}"').scalar_one():
            raise SqliteMigrationDeltaError("environment_migration_generated_state")


def upgrade(connection):
    connection.exec_driver_sql("ALTER TABLE users ADD COLUMN ui_language VARCHAR(2)")
    connection.exec_driver_sql("ALTER TABLE users ADD COLUMN ui_preference_revision INTEGER DEFAULT '0' NOT NULL")
    connection.exec_driver_sql("ALTER TABLE agent_slots ADD COLUMN timezone_revision INTEGER DEFAULT '0' NOT NULL")
    connection.exec_driver_sql("ALTER TABLE local_bot_action_quota_buckets ADD COLUMN period_state JSON")
    connection.exec_driver_sql("ALTER TABLE memory_maintenance_jobs ADD COLUMN environment_snapshot JSON")
    ddl = json.loads(Path(__file__).with_name("environment_v27_ddl.json").read_text(encoding="utf-8"))
    for table in sorted(NEW_TABLES):
        connection.exec_driver_sql(ddl[table]["create"])
        for index in ddl[table]["indexes"]:
            connection.exec_driver_sql(index)
