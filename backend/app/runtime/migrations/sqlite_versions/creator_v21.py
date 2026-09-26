"""Frozen v20→v21 local creator schema. Runs on an unpublished staging DB."""
import hashlib
import json
from pathlib import Path

from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

NEW_TABLES = ("owner_default_worlds", "character_world_bindings", "character_card_sources", "character_registration_receipts")
REBUILT_TABLES = ("worlds", "agent_creation_drafts")
MUTABLE_IDENTITY_TABLES = frozenset((*NEW_TABLES, *REBUILT_TABLES))


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
        added = {"icon_media_id"} if table == "worlds" else {"contract_version", "revision", "target_world_id", "source_kind", "status"}
        columns = tuple(row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})") if row[1] not in added)
        result[table] = (columns, _digest(connection, table, columns))
    return result


def upgrade(connection):
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise SqliteMigrationDeltaError("creator_v21_fk_precondition_failed")
    before = capture_delta(connection)
    definitions = json.loads(Path(__file__).with_name("creator_v21_ddl.json").read_text(encoding="utf-8"))
    for table in REBUILT_TABLES:
        columns = tuple(row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})"))
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
            raise SqliteMigrationDeltaError("creator_v21_existing_data_changed")
    for table in NEW_TABLES:
        if connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one():
            raise SqliteMigrationDeltaError("creator_v21_new_table_not_empty")
    if connection.exec_driver_sql("SELECT COUNT(*) FROM agent_creation_drafts WHERE contract_version != 1 OR revision != 1 OR target_world_id IS NOT NULL OR status != 'editing' OR source_kind != 'direct'").scalar_one():
        raise SqliteMigrationDeltaError("creator_v21_legacy_draft_changed")
