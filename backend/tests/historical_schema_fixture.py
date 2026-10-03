"""Seed frozen SQLite schemas through a separate current-ORM fixture database.

Product ORM columns must never be added to the historical database under test.
Only its explicit frozen columns are copied, with row counts and FK checks.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.runtime.persistence.model_registration import register_models


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
