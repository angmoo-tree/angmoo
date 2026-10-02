"""Reconstruct only synthetic v25 predecessors; never downgrade installed data."""
from sqlalchemy.schema import CreateTable, CreateIndex
from app.runtime.persistence.sqlite_schema import build_sqlite_v25_metadata
from app.runtime.migrations.sqlite_versions.images_v26 import REBUILT_TABLES, NEW_TABLES


def freeze_pre_image_schema(connection):
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
