"""v34 -> v35 parity and staged rollback with populated synthetic receipts."""
from hashlib import sha256
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence import sqlite_schema as schema
from app.runtime.migrations.sqlite_versions import situation_source_binding_v35 as migration, registry
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeCoordinator, SqliteCanonicalUpgradeError
from app.runtime.migrations.generation import EmbeddedGenerationController
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_situation_parent_binding_recovery import historic
from memory.test_situation_recovery_actions import recheck
from memory.test_activity_situation_contract import NOW


def seed(path):
    register_models()
    engine = create_engine(f"sqlite:///{path}")
    schema.build_sqlite_v34_metadata().create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        scope, setting, *_ = _stack(db)
        row, *_ = historic(db, scope)
        recheck(db, setting, row=row)
        # The forward delta must never interpret or rewrite existing ciphertext.
        db.connection().exec_driver_sql("UPDATE llm_credentials SET encrypted_api_key='synthetic-opaque-ciphertext'")
        db.commit()
    with engine.begin() as connection:
        schema.create_schema_version_table(connection)
        manifest = registry.load_sqlite_manifest(34)
        assert schema.sqlite_schema_contract_digest(connection) == manifest.schema_digest
        connection.exec_driver_sql("INSERT INTO angmoo_schema_version VALUES(1,34,?,?,?,?)",
            (manifest.source_revision, manifest.source_migration_count, schema.sqlite_schema_digest(connection), NOW.isoformat()))
    return engine


@pytest.mark.parametrize("alembic", [False, True])
def test_populated_forward_upgrade_matches_orm_and_preserves_all_old_rows(tmp_path, alembic, deny_external_network):
    engine = seed(tmp_path / "v34.sqlite3")
    with engine.begin() as connection:
        previous = {table: connection.exec_driver_sql(f'SELECT * FROM "{table}"').all()
            for table in registry.load_sqlite_manifest(34).table_inventory}
        if alembic:
            path = Path(__file__).parents[2] / "alembic/versions/20261010_0112_situation_source_binding.py"
            spec = importlib.util.spec_from_file_location("source_binding_migration", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.op = Operations(MigrationContext.configure(connection))
            module.upgrade()
        else:
            migration.upgrade(connection)
        migration.verify_delta(connection, None)
        assert schema.sqlite_schema_contract_digest(connection) == registry.load_sqlite_manifest(35).schema_digest
        assert connection.exec_driver_sql("SELECT count(*) FROM memory_situation_source_bindings").scalar_one() == 0
        for table, rows in previous.items():
            assert connection.exec_driver_sql(f'SELECT * FROM "{table}"').all() == rows, table
        migration.upgrade(connection)
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    engine.dispose()


@pytest.mark.parametrize("version", [27, 29, 30, 31, 32, 33, 34, 35])
def test_historical_builders_keep_frozen_schema_contract(tmp_path, version):
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / f'v{version}.sqlite3'}")
    metadata = schema.build_sqlite_baseline_metadata() if version == 35 else getattr(schema, f"build_sqlite_v{version}_metadata")()
    metadata.create_all(engine)
    with engine.begin() as connection:
        schema.create_schema_version_table(connection)
        assert schema.sqlite_schema_contract_digest(connection) == registry.load_sqlite_manifest(version).schema_digest
    engine.dispose()


def test_staging_failure_preserves_db_key_and_selected_generation(tmp_path, monkeypatch, deny_external_network):
    root = tmp_path / "isolated"
    path = root / "canonical/generations/binding-v34/angmoo.sqlite3"
    path.parent.mkdir(parents=True)
    seed(path).dispose()
    secret = root / "secrets/app-secret"
    secret.parent.mkdir()
    secret.write_text("synthetic-preserved-app-secret", encoding="utf-8")
    controller = EmbeddedGenerationController(root / "canonical", artifact_relative_path="angmoo.sqlite3")
    controller.promote("generations/binding-v34", manifest_sha256=registry.load_sqlite_manifest(34).manifest_sha256, data_version=34)
    marker, original, key = controller.current_marker.read_bytes(), sha256(path.read_bytes()).hexdigest(), secret.read_bytes()
    original_upgrade = registry.MIGRATIONS[34]
    def fail(connection):
        original_upgrade(connection)
        raise RuntimeError("injected_after_binding_table")
    monkeypatch.setitem(registry.MIGRATIONS, 34, fail)
    coordinator = SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(root), fallback_generation="binding-v34")
    with pytest.raises(SqliteCanonicalUpgradeError, match="step_failed"):
        coordinator.upgrade()
    assert sha256(path.read_bytes()).hexdigest() == original
    assert controller.current_marker.read_bytes() == marker and secret.read_bytes() == key
    assert not list(controller.generations.glob(".*.tmp-*"))
    monkeypatch.setitem(registry.MIGRATIONS, 34, original_upgrade)
    upgraded = coordinator.upgrade()
    assert upgraded.source_version == 34 and upgraded.target_version == 35
    assert sha256(path.read_bytes()).hexdigest() == original and secret.read_bytes() == key
