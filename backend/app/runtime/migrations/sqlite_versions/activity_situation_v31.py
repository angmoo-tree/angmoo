"""Add durable situations; migration never discards legacy jobs or invokes AI."""
import json
from pathlib import Path

from sqlalchemy import inspect, text
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

NEW_TABLES = frozenset((
    "memory_situation_settings", "memory_situation_manifests", "memory_situation_runs",
    "memory_situation_requests", "memory_situation_receipts", "memory_situation_info",
    "memory_situation_sources", "memory_situation_transitions",
))
MUTABLE_IDENTITY_TABLES = NEW_TABLES


def capture_delta(connection):
    return tuple(connection.execute(text(
        "SELECT scope_setting_id,schedule_enabled,local_time,timezone,shutdown_enabled,next_due_at "
        "FROM memory_batch_settings ORDER BY scope_setting_id"
    )))


def verify_delta(connection, before):
    if capture_delta(connection) != before:
        raise SqliteMigrationDeltaError("situation_historical_settings_changed")
    copied = tuple(connection.execute(text(
        "SELECT scope_setting_id,daily_enabled,local_time,timezone,shutdown_apply_enabled,next_due_at "
        "FROM memory_situation_settings ORDER BY scope_setting_id"
    )))
    if copied != before:
        raise SqliteMigrationDeltaError("situation_schedule_inheritance_failed")
    for table in NEW_TABLES - {"memory_situation_settings"}:
        if connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one():
            raise SqliteMigrationDeltaError("situation_history_recaptured")


def upgrade(connection):
    existing = set(inspect(connection).get_table_names())
    if NEW_TABLES <= existing:
        return
    if NEW_TABLES & existing:
        raise SqliteMigrationDeltaError("situation_partial_schema")
    for statement in json.loads(Path(__file__).with_name("activity_situation_v31_ddl.json").read_text(encoding="utf-8")):
        connection.exec_driver_sql(statement)
    inherit_settings(connection)


def inherit_settings(connection):
    connection.execute(text(
        "INSERT INTO memory_situation_settings "
        "(scope_setting_id,daily_enabled,local_time,timezone,shutdown_apply_enabled,next_due_at,version,updated_at) "
        "SELECT scope_setting_id,schedule_enabled,local_time,timezone,shutdown_enabled,next_due_at,1,updated_at "
        "FROM memory_batch_settings"
    ))
