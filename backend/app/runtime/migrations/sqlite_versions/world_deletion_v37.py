"""Add empty durable erasure tables and canonical write fences; no user erasure."""
import json
from pathlib import Path
from sqlalchemy import inspect
from .contracts import SqliteMigrationDeltaError

MUTABLE_IDENTITY_TABLES = frozenset({"world_deletion_requests", "world_deletion_cleanup_items"})


def capture_delta(connection):
    return None


def verify_delta(connection, before):
    for name in MUTABLE_IDENTITY_TABLES:
        if connection.exec_driver_sql(f'SELECT count(*) FROM "{name}"').scalar_one():
            raise SqliteMigrationDeltaError("world_deletion_migration_not_empty")


def upgrade(connection):
    statements = json.loads(Path(__file__).with_name("world_deletion_v37_ddl.json").read_text(encoding="utf-8"))
    present = set(inspect(connection).get_table_names())
    for entry in statements:
        if entry["table"] not in present:
            connection.exec_driver_sql(entry["create"])
            for sql in entry["indexes"]:
                connection.exec_driver_sql(sql)
    from app.runtime.world_deletion.fences import install_fences
    install_fences(connection)
