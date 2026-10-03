"""Reconstruct only synthetic v25 predecessors; never downgrade installed data."""
from sqlalchemy.schema import CreateTable, CreateIndex
from app.runtime.persistence.sqlite_schema import build_sqlite_v25_metadata
from app.runtime.migrations.sqlite_versions.images_v26 import REBUILT_TABLES, NEW_TABLES


def freeze_pre_image_schema(connection):
    # This helper only reconstructs synthetic predecessors. Strip the later
    # environment additions before the image delta, retaining frozen schemas.
    from app.runtime.persistence.sqlite_environment_schema import (
        ADDED_COLUMNS as ENVIRONMENT_COLUMNS, NEW_TABLES as ENVIRONMENT_TABLES,
    )
    present = {row[0] for row in connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for name in sorted(ENVIRONMENT_TABLES & present):
        connection.exec_driver_sql(f'DROP TABLE "{name}"')
    for name, columns in ENVIRONMENT_COLUMNS.items():
        existing = {row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{name}")')}
        for column in columns:
            if column in existing:
                connection.exec_driver_sql(f'ALTER TABLE "{name}" DROP COLUMN "{column}"')
    metadata=build_sqlite_v25_metadata()
    connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
    try:
        for name in sorted(REBUILT_TABLES):
            table=metadata.tables[name];old=name+"_image_fixture"
            connection.exec_driver_sql(f'ALTER TABLE "{name}" RENAME TO "{old}"')
            connection.execute(CreateTable(table))
            columns=",".join(table.c.keys())
            connection.exec_driver_sql(f'INSERT INTO "{name}" ({columns}) SELECT {columns} FROM "{old}"')
            connection.exec_driver_sql(f'DROP TABLE "{old}"')
            for index in table.indexes:
                connection.execute(CreateIndex(index))
        for name in sorted(NEW_TABLES):
            connection.exec_driver_sql(f'DROP TABLE "{name}"')
    finally:
        connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
