"""Supported historical PostgreSQL upgrade, isolated schemas and controlled races."""
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.runtime.persistence.sqlite_schema import build_sqlite_v27_metadata
from app.runtime.migrations.sqlite_versions import world_configuration_v28 as v28
from app.domains.characters.models import Character
from app.domains.characters.service.import_snapshots import get_import_snapshot
from app.domains.world_characters.service.configuration import effective_configuration
from world_configuration_fixture_support import seed_configuration_fixture


def migrate(connection):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/20261005_0106_world_character_configuration.py"
    spec = importlib.util.spec_from_file_location("test_world_configuration_alembic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()


@pytest.fixture
def postgres(tmp_path):
    value = os.getenv("WORLD_CONFIGURATION_TEST_DATABASE_URL")
    if not value:
        pytest.skip("explicit isolated WORLD_CONFIGURATION_TEST_DATABASE_URL is required")
    url = make_url(value)
    assert url.host in ("127.0.0.1", "localhost") and url.database.startswith("angmoo_world_config_test")
    schema = "world_config_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    source = seed_configuration_fixture(tmp_path / "pg-source.sqlite3", legacy=True)
    metadata = build_sqlite_v27_metadata()
    try:
        metadata.create_all(engine)
        with source.connect() as origin, engine.begin() as target:
            for table in metadata.sorted_tables:
                values = origin.execute(select(table)).mappings().all()
                if values:
                    target.execute(table.insert(), [dict(row) for row in values])
        yield engine
    finally:
        source.dispose()
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


def test_t99_t111_postgres_additive_upgrade_preserves_old_values_and_reentry(postgres):
    with postgres.begin() as connection:
        old = [tuple(row) for row in connection.execute(text("SELECT id,name,personality FROM characters ORDER BY id"))]
        migrate(connection)
        assert old == [tuple(row) for row in connection.execute(text("SELECT id,name,personality FROM characters ORDER BY id"))]
        first = [tuple(row) for row in connection.execute(text("SELECT id,digest,captured_at FROM character_import_snapshots ORDER BY id"))]
        v28.backfill(connection)
        assert first == [tuple(row) for row in connection.execute(text("SELECT id,digest,captured_at FROM character_import_snapshots ORDER BY id"))]
        assert connection.execute(text("SELECT count(*) FROM world_character_configurations")).scalar_one() == 2
    with Session(postgres) as db:
        row, basis = get_import_snapshot(db, "config-actor-a")
        assert row.kind == "legacy_transition" and basis.settings.personality == "Original persona"
        assert effective_configuration(db, world_character_id="config-role-a").revision == 1


def test_t115_postgres_rollback_removes_partial_schema_then_resume(postgres, monkeypatch):
    original = v28.backfill
    def fail(_connection):
        raise RuntimeError("controlled transition failure")
    monkeypatch.setattr(v28, "backfill", fail)
    with pytest.raises(RuntimeError, match="controlled"):
        with postgres.begin() as connection:
            migrate(connection)
    assert not inspect(postgres).has_table("character_import_snapshots")
    assert "input_snapshot" not in {column["name"] for column in inspect(postgres).get_columns("agent_runs")}
    monkeypatch.setattr(v28, "backfill", original)
    with postgres.begin() as connection:
        migrate(connection)
    assert inspect(postgres).has_table("character_import_snapshots")


def test_t115_postgres_source_edit_serializes_behind_transition_lock(postgres):
    frozen, editing = Event(), Event()
    def transition():
        with postgres.begin() as connection:
            migrate(connection)
            frozen.set()
            assert editing.wait(10)
    def edit():
        assert frozen.wait(15)
        with postgres.begin() as connection:
            editing.set()
            connection.execute(text("UPDATE characters SET personality='Later PG source' WHERE id='config-actor-a'"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(transition), pool.submit(edit)
        a.result(25)
        b.result(25)
    with Session(postgres) as db:
        assert db.get(Character, "config-actor-a").personality == "Later PG source"
        assert get_import_snapshot(db, "config-actor-a")[1].settings.personality == "Original persona"
