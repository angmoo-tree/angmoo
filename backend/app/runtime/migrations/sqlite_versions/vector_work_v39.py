"""Add empty projection work ledgers and atomic source signals; no enrollment."""
import json
from pathlib import Path
from .contracts import SqliteMigrationDeltaError

MUTABLE_IDENTITY_TABLES = frozenset({"memory_vector_work", "memory_vector_changes",
    "memory_vector_validation_revisions", "memory_vector_dependencies", "memory_vector_maintenance", "memory_vector_attempts"})


def capture_delta(connection):
    return None


def upgrade(connection):
    for statement in json.loads(Path(__file__).with_name("vector_work_v39_ddl.json").read_text(encoding="utf-8")):
        connection.exec_driver_sql(statement)


def verify_delta(connection, before):
    for name in MUTABLE_IDENTITY_TABLES:
        if connection.exec_driver_sql(f'SELECT count(*) FROM "{name}"').scalar_one():
            raise SqliteMigrationDeltaError("memory_vector_migration_must_start_empty")
