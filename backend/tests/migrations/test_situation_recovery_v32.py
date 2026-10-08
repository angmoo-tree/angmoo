"""Published v31 preservation, schema parity and unpublished-staging rollback."""
from dataclasses import asdict
import hashlib
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import (
    build_sqlite_v31_metadata, build_sqlite_baseline_metadata, create_schema_version_table,
    sqlite_schema_contract_digest, sqlite_schema_digest,
)
from app.runtime.migrations.sqlite_versions import situation_recovery_v32
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.models.activity_situation import MemorySituationManifest
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_application import real_source
from memory.test_activity_situation_contract import NOW, values


def seed_v31(path):
    register_models()
    engine = create_engine(f"sqlite:///{path}")
    metadata = build_sqlite_v31_metadata()
    metadata.create_all(engine)
    with Session(engine) as db:
        scope, setting, *_ = _stack(db)
        post = real_source(db, scope)
        manifest, draft, result = values(db, scope, target=post.id)
        payload = asdict(result)
        payload["result_sources"] = []
        payload["occurred_at"] = result.occurred_at.isoformat()
        original = manifest.to_dict()
        digest = stable_digest(original)
        db.add(MemorySituationManifest(id=digest, scope_setting_id=setting.id,
            call_identity=manifest.call_identity, content_digest=digest, payload=original, created_at=NOW))
        db.flush()
        db.execute(metadata.tables["memory_situation_runs"].insert().values(
            id="old-completed-run", scope_setting_id=setting.id, trigger="manual", request_identity="old-save-request-001",
            cutoff_sequence=1, cursor=1, settings_snapshot={"version": 1}, state="completed", attempts=1,
            applied_count=0, blocked_count=1, skipped_count=0, created_at=NOW, completed_at=NOW))
        db.execute(metadata.tables["memory_situation_receipts"].insert().values(
            sequence=1, scope_setting_id=setting.id, logical_activity_id=result.logical_activity_id,
            lane=result.lane, target_key=result.target_key, manifest_id=digest, policy_version=manifest.snapshot.policy_version,
            activation_epoch=manifest.snapshot.activation_epoch, scope_version=manifest.snapshot.scope_version,
            content_digest=stable_digest({"manifest": original, "draft": asdict(draft), "result": payload}),
            description=draft.description, description_status=draft.status, result=payload,
            occurred_at=NOW, captured_at=NOW, state="blocked", error_code="situation_source_changed_or_forbidden",
            run_id="old-completed-run"))
        legacy_key_digest = stable_digest({"scope": asdict(scope), "trigger": "manual", "version": 1})
        db.execute(metadata.tables["memory_situation_requests"].insert().values(
            scope_setting_id=setting.id, request_key="old-save-request-001", request_digest=legacy_key_digest,
            run_id="old-completed-run", result_code="accepted", created_at=NOW))
        db.commit()
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE sqlite_sequence SET seq=500 WHERE name='memory_situation_receipts'")
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(31).schema_digest
        connection.exec_driver_sql("INSERT INTO angmoo_schema_version VALUES(1,31,'20261008_0108',107,?,?)",
            (sqlite_schema_digest(connection), NOW.isoformat()))
    return engine


@pytest.mark.parametrize("alembic", [False, True])
def test_populated_v31_delta_preserves_every_old_column_and_high_water_sequence(tmp_path, alembic):
    engine = seed_v31(tmp_path / "old.sqlite3")
    with engine.begin() as connection:
        original = {table: tuple(connection.exec_driver_sql(f'SELECT * FROM "{table}"'))
            for table in load_sqlite_manifest(31).table_inventory
            if table not in situation_recovery_v32.MUTABLE_IDENTITY_TABLES}
        before = situation_recovery_v32.capture_delta(connection)
        if alembic:
            path = Path(__file__).parents[2] / "alembic/versions/20261008_0109_situation_recovery.py"
            spec = importlib.util.spec_from_file_location("recovery_migration", path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
        else:
            situation_recovery_v32.upgrade(connection)
        situation_recovery_v32.verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(32).schema_digest
        assert connection.exec_driver_sql("SELECT state,state_version,manifest_id FROM memory_situation_receipts").one()[:2] == ("blocked", 1)
        for table, rows in original.items():
            assert tuple(connection.exec_driver_sql(f'SELECT * FROM "{table}"')) == rows, table
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    engine.dispose()


def test_fresh_orm_matches_frozen_v32_manifest(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.sqlite3'}")
    register_models()
    build_sqlite_baseline_metadata().create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(32).schema_digest
    engine.dispose()


@pytest.mark.parametrize("sequence", [None, 0])
@pytest.mark.parametrize("alembic", [False, True])
def test_empty_predecessor_preserves_the_exact_sequence_marker(tmp_path, sequence, alembic):
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'empty-v31.sqlite3'}")
    build_sqlite_v31_metadata().create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(31).schema_digest
        if sequence is not None:
            connection.exec_driver_sql("INSERT INTO sqlite_sequence(name,seq) VALUES('memory_situation_receipts',?)", (sequence,))
        before = situation_recovery_v32.capture_delta(connection)
        assert before["sequence"] == sequence
        if alembic:
            path = Path(__file__).parents[2] / "alembic/versions/20261008_0109_situation_recovery.py"
            spec = importlib.util.spec_from_file_location("empty_recovery_migration", path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
        else:
            situation_recovery_v32.upgrade(connection)
        situation_recovery_v32.verify_delta(connection, before)
        assert connection.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name='memory_situation_receipts'").scalar() == sequence
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(32).schema_digest
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    engine.dispose()


def test_staging_failure_keeps_original_database_and_selected_marker(tmp_path, monkeypatch):
    from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
    from app.runtime.migrations.generation import EmbeddedGenerationController
    from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeCoordinator, SqliteCanonicalUpgradeError
    from app.runtime.migrations.sqlite_versions import registry
    root = tmp_path / "isolated-runtime"
    path = root / "canonical/generations/v31-fixture/angmoo.sqlite3"
    path.parent.mkdir(parents=True)
    seed_v31(path).dispose()
    controller = EmbeddedGenerationController(root / "canonical", artifact_relative_path="angmoo.sqlite3")
    controller.promote("generations/v31-fixture", manifest_sha256=load_sqlite_manifest(31).manifest_sha256, data_version=31)
    marker = controller.current_marker.read_bytes()
    original_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    original = registry.MIGRATIONS[31]
    def fail(connection):
        original(connection)
        raise RuntimeError("injected_after_table_rebuild")
    monkeypatch.setitem(registry.MIGRATIONS, 31, fail)
    with pytest.raises(SqliteCanonicalUpgradeError, match="step_failed"):
        SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(root), fallback_generation="v31-fixture").upgrade()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_sha
    assert controller.current_marker.read_bytes() == marker
    assert not list(controller.generations.glob(".*.tmp-*"))
    monkeypatch.setitem(registry.MIGRATIONS, 31, original)
    result = SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(root), fallback_generation="v31-fixture").upgrade()
    assert result.source_version == 31 and result.target_version == 32 and result.migrated
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_sha
