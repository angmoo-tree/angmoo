import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from app.runtime.persistence.model_registration import register_models

from app.runtime.persistence.sqlite_schema import (
    build_sqlite_v13_metadata, build_sqlite_v12_metadata,
    create_schema_version_table, sqlite_schema_contract_digest,
)


def test_episode_alembic_matches_embedded_and_roundtrips(tmp_path):
    register_models()
    before = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'old.sqlite').as_posix()}")
    fresh = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'new.sqlite').as_posix()}")
    build_sqlite_v12_metadata().create_all(before)
    build_sqlite_v13_metadata().create_all(fresh)
    for engine in (before, fresh):
        with engine.begin() as connection:
            create_schema_version_table(connection)
    with fresh.connect() as connection:
        expected = sqlite_schema_contract_digest(connection)
    with before.connect() as connection:
        original = sqlite_schema_contract_digest(connection)
    path = Path(__file__).parents[2] / "alembic/versions/20260916_0093_episode_memory.py"
    spec = importlib.util.spec_from_file_location("episode_migration_0093", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    for operation, digest in (("upgrade", expected), ("downgrade", original), ("upgrade", expected)):
        with before.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            getattr(migration, operation)()
            assert sqlite_schema_contract_digest(connection) == digest
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    before.dispose()
    fresh.dispose()
