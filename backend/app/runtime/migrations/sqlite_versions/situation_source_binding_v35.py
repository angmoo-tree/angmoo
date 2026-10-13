"""Forward empty resolution storage. Never repairs receipts during migration."""
import json
from pathlib import Path
from sqlalchemy import inspect
from .contracts import SqliteMigrationDeltaError

MUTABLE_IDENTITY_TABLES = frozenset({"memory_situation_source_bindings"})


def capture_delta(connection):
    return None


def verify_delta(connection, before):
    if connection.exec_driver_sql("SELECT count(*) FROM memory_situation_source_bindings").scalar_one():
        raise SqliteMigrationDeltaError("situation_binding_migration_not_empty")


def upgrade(connection):
    if "memory_situation_source_bindings" not in inspect(connection).get_table_names():
        for statement in json.loads(Path(__file__).with_name("situation_source_binding_v35_ddl.json").read_text(encoding="utf-8")):
            connection.exec_driver_sql(statement)
