"""Published v32 remains intact; v33 is a staged, nullable formal delta."""
from datetime import UTC, datetime
import hashlib
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import (build_sqlite_baseline_metadata, build_sqlite_v32_metadata,
    create_schema_version_table, sqlite_schema_contract_digest, sqlite_schema_digest)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeCoordinator, SqliteCanonicalUpgradeError
from app.runtime.migrations.sqlite_versions import comfy_diagnostics_v33, registry
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest


def seed(path):
    register_models(); metadata = build_sqlite_v32_metadata()
    engine = create_engine(f"sqlite:///{path}")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(metadata.tables["users"].insert().values(id="owner", display_name="synthetic"))
        connection.execute(metadata.tables["characters"].insert().values(id="bird", owner_id="owner", name="Bird", handle="bird", persona_summary="unchanged"))
        connection.execute(metadata.tables["posts"].insert().values(id="post", author_character_id="bird", author_name="Bird", title="old", body="keep"))
        connection.execute(metadata.tables["post_image_generation_jobs"].insert().values(post_id="post", character_id="bird", user_id="owner", source="routine", status="outcome_unknown", provider_receipt="old-receipt", image_model="workflow", image_prompt="old prompt", prompt_hash="a"*64, key_source="user"))
        create_schema_version_table(connection)
        manifest = load_sqlite_manifest(32)
        assert sqlite_schema_contract_digest(connection) == manifest.schema_digest
        connection.exec_driver_sql("INSERT INTO angmoo_schema_version VALUES(1,32,?,?,?,?)", (manifest.source_revision, manifest.source_migration_count, sqlite_schema_digest(connection), datetime.now(UTC).isoformat()))
    return engine


@pytest.mark.parametrize("alembic", [False, True])
def test_both_migration_paths_preserve_old_rows_and_match_current_orm(tmp_path, alembic):
    engine = seed(tmp_path / "v32.sqlite3")
    with engine.begin() as connection:
        before = comfy_diagnostics_v33.capture_delta(connection)
        if alembic:
            path = Path(__file__).parents[2] / "alembic/versions/20261009_0110_comfy_diagnostics.py"
            spec = importlib.util.spec_from_file_location("comfy_migration", path)
            migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
            migration.op = Operations(MigrationContext.configure(connection)); migration.upgrade()
        else:
            comfy_diagnostics_v33.upgrade(connection)
        comfy_diagnostics_v33.verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(33).schema_digest
        assert connection.exec_driver_sql("SELECT provider_receipt,status,provider_diagnostic_json FROM post_image_generation_jobs").one() == ("old-receipt", "outcome_unknown", None)
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    engine.dispose()
    fresh = create_engine("sqlite://")
    build_sqlite_baseline_metadata().create_all(fresh)
    with fresh.begin() as connection:
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(33).schema_digest
    fresh.dispose()


@pytest.mark.parametrize("fail", [False, True])
def test_staged_upgrade_preserves_source_even_if_ddl_fails(tmp_path, monkeypatch, fail):
    source = tmp_path / "canonical/generations/comfy-v32/angmoo.sqlite3"
    source.parent.mkdir(parents=True); seed(source).dispose()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    if fail:
        def interrupted(connection):
            comfy_diagnostics_v33.upgrade(connection)
            raise RuntimeError("synthetic-ddl-failure")
        monkeypatch.setitem(registry.MIGRATIONS, 32, interrupted)
        with pytest.raises(SqliteCanonicalUpgradeError):
            SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation="comfy-v32").upgrade()
        assert not (tmp_path / "canonical/current-generation.json").exists()
        assert not list(source.parent.parent.glob(".*.tmp-*"))
    else:
        result = SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation="comfy-v32").upgrade()
        assert result.source_version == 32 and result.target_version == 33 and result.database_path != source
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
