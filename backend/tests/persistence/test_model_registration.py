"""Cold model registration and explicit/default DB ownership stay independent."""

import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import text


BACKEND = Path(__file__).resolve().parents[2]


def run_cold(source, *args):
    result = subprocess.run(
        [sys.executable, "-c", source, *map(str, args)],
        cwd=BACKEND,
        env={**os.environ, "APP_ENV": "test", "PYTHONPATH": str(BACKEND)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_base_import_does_not_load_domain_models_database_or_runtime():
    result = run_cold("""
import sys
from app.models import Base
assert len(Base.metadata.tables) == 0
assert 'app.database' not in sys.modules
assert not any(name.startswith('app.runtime') for name in sys.modules)
assert not any(name.startswith('app.domains') for name in sys.modules)
""")
    assert result == ""


def test_registration_is_idempotent_and_keeps_102_canonical_classes():
    result = run_cold("""
from app.models import Base
from app.runtime.persistence.model_registration import register_models
import app.database as database
from sqlalchemy.orm import configure_mappers
metadata = register_models()
configure_mappers()
original = {mapper.class_.__tablename__: mapper.class_ for mapper in Base.registry.mappers}
assert len(original) == len(metadata.tables) == 102
assert register_models() is metadata is Base.metadata
assert {mapper.class_.__tablename__: mapper.class_ for mapper in Base.registry.mappers} == original
assert all(model.metadata is metadata for model in original.values())
assert all(model.__module__.startswith('app.domains.') for model in original.values())
assert database._default_engine is None
assert database._default_session_factory is None
from app.core.db import Base as frozen_migration_base
assert frozen_migration_base is Base
""")
    assert result == ""


def test_canonical_database_opens_without_importing_an_app(tmp_path):
    result = run_cold("""
from pathlib import Path
import sys
from app.runtime.persistence import SqliteCanonicalDatabase, StaticRuntimeDataPath
import app.database as defaults
database = SqliteCanonicalDatabase(StaticRuntimeDataPath(Path(sys.argv[1])))
try:
    first = database.open()
    engine = database.engine
    second = database.open()
    assert database.engine is engine
    assert first.schema_version == second.schema_version == 9
    assert first.canonical_table_count == second.canonical_table_count == 102
    assert first.schema_digest_matches and second.schema_digest_matches
    assert first.foreign_keys and first.synchronous == 'FULL'
    assert 'app.main' not in sys.modules and 'app.public_main' not in sys.modules
    assert defaults._default_engine is None
finally:
    database.close()
""", tmp_path)
    assert result == ""


def test_default_engine_cache_and_request_session_cleanup(monkeypatch):
    import app.database as database

    calls = []
    engine = object()

    class Session:
        def close(self):
            calls.append("close")

    def create_engine(url):
        calls.append(("engine", url))
        return engine

    def create_factory(value):
        assert value is engine
        calls.append("factory")
        return Session

    monkeypatch.setattr(database, "_default_engine", None)
    monkeypatch.setattr(database, "_default_session_factory", None)
    monkeypatch.setattr(database, "create_database_engine", create_engine)
    monkeypatch.setattr(database, "create_session_factory", create_factory)
    assert database.get_default_engine() is engine
    assert database.get_default_engine() is engine
    assert database.get_default_session_factory() is Session
    assert calls == [("engine", database.settings.database_url), "factory"]
    request = database.get_db()
    assert isinstance(next(request), Session)
    request.close()
    assert calls[-1] == "close"


def test_sqlite_connection_pragmas_and_explicit_session_rollback(tmp_path):
    from app.database import create_database_engine, create_session_factory

    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'explicit.sqlite3'}")
    factory = create_session_factory(engine)
    try:
        with engine.begin() as connection:
            actual = {
                name: connection.exec_driver_sql(f"PRAGMA {name}").scalar_one()
                for name in ("foreign_keys", "busy_timeout", "journal_mode", "synchronous", "wal_autocheckpoint")
            }
            assert actual == {"foreign_keys": 1, "busy_timeout": 5000, "journal_mode": "wal", "synchronous": 2, "wal_autocheckpoint": 1000}
            connection.exec_driver_sql("CREATE TABLE rollback_probe (value TEXT)")
        with factory() as session:
            assert session.autoflush is False
            session.execute(text("INSERT INTO rollback_probe VALUES ('pending')"))
            session.rollback()
        with factory() as observer:
            assert observer.execute(text("SELECT count(*) FROM rollback_probe")).scalar_one() == 0
    finally:
        engine.dispose()
