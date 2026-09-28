"""Frozen v22→v23 plan-source migration, on the unpublished backup generation."""
import hashlib
import json
from pathlib import Path

from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

REBUILT_TABLES = ("daily_activity_plans", "daily_activity_plan_items")
NEW_TABLES = ("activity_preparation_jobs",)
MUTABLE_IDENTITY_TABLES = frozenset((*REBUILT_TABLES, *NEW_TABLES))


def _digest(connection, table, columns):
    digest = hashlib.sha256()
    count = 0
    for row in connection.exec_driver_sql(f"SELECT {','.join(columns)} FROM {table} ORDER BY id"):
        digest.update(json.dumps(tuple(row), default=str, ensure_ascii=False).encode())
        count += 1
    return count, digest.hexdigest()


def capture_delta(connection):
    result = {}
    for table in REBUILT_TABLES:
        columns = tuple(row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})"))
        result[table] = (columns, _digest(connection, table, columns))
    return result


def upgrade(connection):
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise SqliteMigrationDeltaError("daily_preparation_fk_precondition")
    before = capture_delta(connection)
    definitions = json.loads(Path(__file__).with_name("daily_preparation_v23_ddl.json").read_text(encoding="utf-8"))
    for table in REBUILT_TABLES:
        columns = before[table][0]
        joined = ",".join(columns)
        connection.exec_driver_sql(f"CREATE TEMP TABLE copy_{table} AS SELECT {joined} FROM {table}")
        connection.exec_driver_sql(f"DROP TABLE {table}")
        connection.exec_driver_sql(definitions[table]["ddl"])
        connection.exec_driver_sql(f"INSERT INTO {table} ({joined}) SELECT {joined} FROM copy_{table}")
        connection.exec_driver_sql(f"DROP TABLE copy_{table}")
        for sql in definitions[table]["indexes"]:
            connection.exec_driver_sql(sql)
    for table in NEW_TABLES:
        connection.exec_driver_sql(definitions[table]["ddl"])
        for sql in definitions[table]["indexes"]:
            connection.exec_driver_sql(sql)
    verify_delta(connection, before)


def verify_delta(connection, before):
    for table, (columns, expected) in before.items():
        if _digest(connection, table, columns) != expected:
            raise SqliteMigrationDeltaError("daily_preparation_existing_data_changed")
    if connection.exec_driver_sql("SELECT COUNT(*) FROM activity_preparation_jobs").scalar_one():
        raise SqliteMigrationDeltaError("daily_preparation_jobs_not_empty")
    if connection.exec_driver_sql("SELECT COUNT(*) FROM daily_activity_plans WHERE generation_source != 'repertoire' OR preparation_contract_version != 'repertoire-v1'").scalar_one():
        raise SqliteMigrationDeltaError("daily_preparation_legacy_source_changed")
