"""New work schema never changes historical rows, vectors or enrollment."""
import pytest
from sqlalchemy import create_engine
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence import sqlite_schema as schema
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions import vector_work_v39 as migration
from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.projection_fixture import index


@pytest.mark.parametrize("version", (1, 8, 19, 37, 38, 39))
def test_frozen_schema_manifests_and_current_trigger_parity(version):
    register_models()
    metadata = schema.build_sqlite_baseline_metadata() if version == 39 else getattr(schema, f"build_sqlite_v{version}_metadata")()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        schema.create_schema_version_table(connection)
        assert schema.sqlite_schema_contract_digest(connection) == load_sqlite_manifest(version).schema_digest
        triggers = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'memory_vector_%'").all()
        assert bool(triggers) == (version == 39)
    engine.dispose()


def test_populated_memory_credentials_and_vector_hash_survive_v38_upgrade(runtime_factory, index, monkeypatch, tmp_path):
    import asyncio
    import hashlib
    from memory.test_vector_projection_lifecycle import setup_projection_scope
    from memory.test_vector_pending_work import Provider
    from app.runtime.memory.vector_projection import MemoryVectorProjection
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    assert asyncio.run(MemoryVectorProjection(runtime_factory, index, provider=Provider()).sync_item(item)) == "indexed"
    vector_hash = hashlib.sha256(index.path.read_bytes()).hexdigest()
    historical = schema.build_sqlite_v38_metadata()
    engine = create_engine(f"sqlite:///{tmp_path / 'populated-v38.sqlite3'}")
    originals = {}
    with runtime_factory.kw["bind"].connect() as source, engine.begin() as target:
        historical.create_all(target)
        schema.create_schema_version_table(target)
        for name, table in historical.tables.items():
            columns = ','.join(f'"{column.name}"' for column in table.columns)
            rows = source.exec_driver_sql(f'SELECT {columns} FROM "{name}"').all()
            originals[name] = sorted((tuple(row) for row in rows), key=repr)
            if rows:
                placeholders = ','.join('?' for _ in table.columns)
                target.exec_driver_sql(f'INSERT INTO "{name}" ({columns}) VALUES ({placeholders})', [tuple(row) for row in rows])
        assert target.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    assert originals["memory_vector_eligibility"] and originals["world_credential_revisions"]
    with engine.begin() as target:
        migration.upgrade(target)
        migration.verify_delta(target, None)
        for name, table in historical.tables.items():
            columns = ','.join(f'"{column.name}"' for column in table.columns)
            assert sorted((tuple(row) for row in target.exec_driver_sql(f'SELECT {columns} FROM "{name}"')), key=repr) == originals[name]
        assert schema.sqlite_schema_contract_digest(target) == load_sqlite_manifest(39).schema_digest
    assert hashlib.sha256(index.path.read_bytes()).hexdigest() == vector_hash
    engine.dispose()


def test_populated_v38_is_unchanged_and_upgrade_is_transactional(tmp_path):
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'v38.sqlite3'}")
    with engine.begin() as connection:
        schema.build_sqlite_v38_metadata().create_all(connection)
        schema.create_schema_version_table(connection)
        connection.exec_driver_sql("INSERT INTO users(id,email,display_name,is_admin,profile_setup_completed) VALUES ('owner','fixture@example.test','fixture',0,1)")
        before = tuple(connection.exec_driver_sql("SELECT * FROM users").all())
        assert schema.sqlite_schema_contract_digest(connection) == load_sqlite_manifest(38).schema_digest
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        migration.upgrade(connection)
        connection.rollback()
        assert schema.sqlite_schema_contract_digest(connection) == load_sqlite_manifest(38).schema_digest
        connection.rollback()
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        snapshot = migration.capture_delta(connection)
        migration.upgrade(connection)
        migration.verify_delta(connection, snapshot)
        assert tuple(connection.exec_driver_sql("SELECT * FROM users").all()) == before
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert schema.sqlite_schema_contract_digest(connection) == load_sqlite_manifest(39).schema_digest
        connection.commit()
    engine.dispose()
