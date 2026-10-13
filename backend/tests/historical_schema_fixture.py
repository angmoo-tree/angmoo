"""Seed frozen SQLite schemas through a separate current-ORM fixture database.

Product ORM columns must never be added to the historical database under test.
Only its explicit frozen columns are copied, with row counts and FK checks.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.runtime.persistence.model_registration import register_models


def rebuild_frozen_schema(connection, metadata):
    """Replace a synthetic current fixture with exactly its frozen predecessor.

    Keep only explicitly declared historical columns, without current tables or
    write-fence triggers. Never apply this helper to application/user databases.
    """
    from sqlalchemy import inspect

    assert connection.dialect.name == "sqlite"
    rows = {}
    for name, table in metadata.tables.items():
        columns = ','.join('"' + c.name.replace('"', '""') + '"' for c in table.columns)
        quoted = '"' + name.replace('"', '""') + '"'
        rows[name] = (columns, connection.exec_driver_sql(f"SELECT {columns} FROM {quoted}").all())
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    for (name,) in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").all():
        quoted = '"' + name.replace('"', '""') + '"'
        connection.exec_driver_sql(f"DROP TRIGGER {quoted}")
    for name in inspect(connection).get_table_names():
        if name == "angmoo_schema_version":
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        connection.exec_driver_sql(f"DROP TABLE {quoted}")
    metadata.create_all(connection)
    for name, (columns, values) in rows.items():
        quoted = '"' + name.replace('"', '""') + '"'
        if values:
            placeholders = ','.join('?' for _ in metadata.tables[name].columns)
            connection.exec_driver_sql(
                f"INSERT INTO {quoted} ({columns}) VALUES ({placeholders})",
                [tuple(row) for row in values],
            )
        assert connection.exec_driver_sql(f"SELECT COUNT(*) FROM {quoted}").scalar_one() == len(values)
    assert set(inspect(connection).get_table_names()) == set(metadata.tables) | {"angmoo_schema_version"}
    assert connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").all() == []
    assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def populate_frozen_schema(engine, metadata, seed):
    source = create_engine("sqlite:///:memory:")
    register_models().create_all(source)
    try:
        with Session(source, expire_on_commit=False) as db:
            result = seed(db)
            db.commit()
        with source.connect() as original, engine.begin() as target:
            target.exec_driver_sql("PRAGMA foreign_keys=OFF")
            for name, table in metadata.tables.items():
                columns = ','.join('"' + c.name.replace('"', '""') + '"' for c in table.columns)
                quoted = '"' + name.replace('"', '""') + '"'
                rows = original.exec_driver_sql(f"SELECT {columns} FROM {quoted}").all()
                if rows:
                    placeholders = ','.join('?' for _ in table.columns)
                    target.exec_driver_sql(
                        f"INSERT INTO {quoted} ({columns}) VALUES ({placeholders})",
                        [tuple(row) for row in rows],
                    )
                assert target.exec_driver_sql(f"SELECT COUNT(*) FROM {quoted}").scalar_one() == len(rows)
            assert target.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        return result
    finally:
        source.dispose()
