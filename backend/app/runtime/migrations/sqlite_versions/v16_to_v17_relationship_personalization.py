"""Preserve existing states and add dormant interpretation/review bookkeeping."""

from sqlalchemy import Connection
from app.runtime.migrations.sqlite_versions.relationship_v17_ddl import (
    TABLES, NEW_TABLE_DDL, NEW_INDEX_DDL, OUTBOX_DDL, OUTBOX_INDEX_DDL, OLD_OUTBOX_COLUMNS,
)

MUTABLE_IDENTITY_TABLES = frozenset((*TABLES, "relationship_states", "graph_projection_outbox"))


def capture_delta(connection: Connection):
    return {name: [dict(row) for row in connection.exec_driver_sql(f"SELECT * FROM {name} ORDER BY id").mappings()]
            for name in ("relationship_states", "graph_projection_outbox")}


def upgrade(connection: Connection):
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one():
        raise RuntimeError("relationship_upgrade_requires_foreign_keys_off")
    for name, definition in (
        ("relationship_label", "VARCHAR(32)"), ("perception", "VARCHAR(300)"),
        ("view_version", "INTEGER DEFAULT '1' NOT NULL"), ("view_updated_at", "DATETIME"),
        ("reviewed_at", "DATETIME"), ("last_metric_at", "DATETIME"),
    ):
        connection.exec_driver_sql(f"ALTER TABLE relationship_states ADD COLUMN {name} {definition}")
    connection.exec_driver_sql("PRAGMA legacy_alter_table = ON")
    try:
        connection.exec_driver_sql("ALTER TABLE graph_projection_outbox RENAME TO graph_projection_outbox_before_ri")
        connection.exec_driver_sql(OUTBOX_DDL)
        connection.exec_driver_sql(f"INSERT INTO graph_projection_outbox ({OLD_OUTBOX_COLUMNS}) SELECT {OLD_OUTBOX_COLUMNS} FROM graph_projection_outbox_before_ri")
        connection.exec_driver_sql("DROP TABLE graph_projection_outbox_before_ri")
        for statement in OUTBOX_INDEX_DDL:
            connection.exec_driver_sql(statement)
    finally:
        connection.exec_driver_sql("PRAGMA legacy_alter_table = OFF")
    for statement in (*NEW_TABLE_DDL, *NEW_INDEX_DDL):
        connection.exec_driver_sql(statement)


def verify_delta(connection: Connection, before):
    for name, rows in before.items():
        after = [dict(row) for row in connection.exec_driver_sql(f"SELECT * FROM {name} ORDER BY id").mappings()]
        if len(after) != len(rows) or any(any(new[key] != value for key, value in old.items()) for old, new in zip(rows, after, strict=True)):
            raise RuntimeError("relationship_upgrade_existing_data_changed")
    for name in TABLES:
        if connection.exec_driver_sql(f"SELECT count(*) FROM {name}").scalar_one():
            raise RuntimeError("relationship_upgrade_automatic_activation_forbidden")
