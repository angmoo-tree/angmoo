"""v35 -> v36 staged delta must preserve populated history and secrets."""
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
from app.runtime.migrations.sqlite_versions import registry, situation_result_binding_v36 as migration
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeCoordinator, SqliteCanonicalUpgradeError
from app.runtime.migrations.generation import EmbeddedGenerationController
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_situation_parent_binding_recovery import historic
from memory.test_activity_situation_contract import NOW


def seed(path):
    register_models()
    engine=create_engine(f"sqlite:///{path}")
    register_models().create_all(engine)
    with Session(engine) as db:
        scope, setting, *_=_stack(db)
        historic(db,scope)
        db.connection().exec_driver_sql("UPDATE llm_credentials SET encrypted_api_key='synthetic-opaque'")
        db.commit()
    with engine.begin() as con:
        schema.create_schema_version_table(con)
        from historical_schema_fixture import rebuild_frozen_schema
        rebuild_frozen_schema(con, schema.build_sqlite_v35_metadata())
        manifest=registry.load_sqlite_manifest(35)
        assert schema.sqlite_schema_contract_digest(con)==manifest.schema_digest
        con.exec_driver_sql("INSERT INTO angmoo_schema_version VALUES(1,35,?,?,?,?)",
            (manifest.source_revision,manifest.source_migration_count,schema.sqlite_schema_digest(con),NOW.isoformat()))
    return engine


@pytest.mark.parametrize("alembic",[False,True])
def test_empty_forward_delta_preserves_every_v35_row(tmp_path,alembic,deny_external_network):
    engine=seed(tmp_path/'source.sqlite')
    with engine.begin() as con:
        before={table:con.exec_driver_sql(f'SELECT * FROM "{table}"').all() for table in registry.load_sqlite_manifest(35).table_inventory}
        if alembic:
            path=Path(__file__).parents[2]/'alembic/versions/20261010_0113_situation_result_binding.py'
            spec=importlib.util.spec_from_file_location('result_binding_migration',path)
            module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            module.op=Operations(MigrationContext.configure(con)); module.upgrade()
        else: migration.upgrade(con)
        migration.verify_delta(con,None)
        assert schema.sqlite_schema_contract_digest(con)==registry.load_sqlite_manifest(36).schema_digest
        assert con.exec_driver_sql('SELECT count(*) FROM memory_situation_result_bindings').scalar_one()==0
        for table,rows in before.items(): assert con.exec_driver_sql(f'SELECT * FROM "{table}"').all()==rows,table
        assert not con.exec_driver_sql('PRAGMA foreign_key_check').all()
        migration.upgrade(con)
    engine.dispose()


def test_staging_failure_preserves_original_generation_key_marker(tmp_path,monkeypatch,deny_external_network):
    root=tmp_path/'isolated'
    path=root/'canonical/generations/v35/angmoo.sqlite3'; path.parent.mkdir(parents=True)
    seed(path).dispose()
    secret=root/'secrets/app-secret'; secret.parent.mkdir(); secret.write_text('synthetic-preserved-key')
    controller=EmbeddedGenerationController(root/'canonical',artifact_relative_path='angmoo.sqlite3')
    controller.promote('generations/v35',manifest_sha256=registry.load_sqlite_manifest(35).manifest_sha256,data_version=35)
    before=sha256(path.read_bytes()).hexdigest(),controller.current_marker.read_bytes(),secret.read_bytes()
    original=registry.MIGRATIONS[35]
    def fail(con): original(con); raise RuntimeError('injected_result_binding_failure')
    monkeypatch.setitem(registry.MIGRATIONS,35,fail)
    coordinator=SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(root),fallback_generation='v35')
    with pytest.raises(SqliteCanonicalUpgradeError,match='step_failed'): coordinator.upgrade()
    assert before==(sha256(path.read_bytes()).hexdigest(),controller.current_marker.read_bytes(),secret.read_bytes())
    monkeypatch.setitem(registry.MIGRATIONS,35,original)
    result=coordinator.upgrade()
    assert (result.source_version,result.target_version)==(35,schema.SQLITE_SCHEMA_VERSION)
    assert sha256(path.read_bytes()).hexdigest()==before[0] and secret.read_bytes()==before[2]
