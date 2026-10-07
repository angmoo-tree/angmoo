"""Compare runtime diagnostics with the schema actually created by the product."""
from pathlib import Path
from dataclasses import replace

from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.domains.runtime.constants import RuntimeDiagnosticCode
from app.domains.runtime.contracts.status import RuntimeComponentState
from app.runtime.diagnostics.status_composition import create_runtime_status_reader
from app.runtime.diagnostics import status_composition
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_database import SqliteCanonicalDatabase
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION, SOURCE_ALEMBIC_REVISION


def test_diagnostic_head_matches_shipped_sqlite_manifest_and_alembic_graph():
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic"))
    manifest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with Session(engine) as session:
            diagnostic = create_runtime_status_reader(
                session, config=Settings(DATABASE_URL=str(engine.url)),
            )._migration_status()
        assert diagnostic.head_revision == manifest.source_revision
        assert diagnostic.head_revision == SOURCE_ALEMBIC_REVISION
        assert scripts.get_heads() == [diagnostic.head_revision]
        # Frozen v30 retains its exact Alembic predecessor independently of
        # which schema becomes the next shipped diagnostic target.
        assert scripts.get_revision(load_sqlite_manifest(30).source_revision).down_revision == load_sqlite_manifest(29).source_revision
    finally:
        engine.dispose()
    # The released v19 marker retains its older lineage.
    assert load_sqlite_manifest(19).source_revision == "20260918_0096"


@pytest.mark.parametrize("replacement", [None, "20261005_0106", "20260825_0083", "20990101_9999"])
def test_real_canonical_database_diagnostic_accepts_only_current_revision(tmp_path, replacement):
    register_models()
    database = SqliteCanonicalDatabase(StaticRuntimeDataPath(tmp_path))
    try:
        doctor = database.open()
        config = Settings(DATABASE_URL=database.engine.url.render_as_string())
        with database.session() as session:
            if replacement is not None:
                session.execute(text("UPDATE angmoo_schema_version SET source_revision=:revision"),
                                {"revision": replacement})
                session.commit()
            status = create_runtime_status_reader(session, config=config)._migration_status()
            assert status.head_revision == doctor.source_revision
            assert status.current_revision == (replacement or doctor.source_revision)
            if replacement is None:
                assert status.state is RuntimeComponentState.READY
                assert status.reason_code is None
            else:
                assert status.state is RuntimeComponentState.DEGRADED
                assert status.reason_code is RuntimeDiagnosticCode.MIGRATION_NOT_CURRENT
    finally:
        database.close()


def test_diagnostics_follow_a_new_shipped_manifest_without_a_domain_version_constant(tmp_path, monkeypatch):
    register_models()
    database = SqliteCanonicalDatabase(StaticRuntimeDataPath(tmp_path))
    try:
        doctor = database.open()
        next_manifest = replace(load_sqlite_manifest(SQLITE_SCHEMA_VERSION),
                                schema_version=SQLITE_SCHEMA_VERSION + 1,
                                source_revision="20990101_9999")

        def packaged_manifest(version):
            assert version == next_manifest.schema_version
            return next_manifest

        monkeypatch.setattr(status_composition, "SQLITE_SCHEMA_VERSION", next_manifest.schema_version)
        monkeypatch.setattr(status_composition, "load_sqlite_manifest", packaged_manifest)
        config = Settings(DATABASE_URL=database.engine.url.render_as_string())
        with database.session() as session:
            status = create_runtime_status_reader(session, config=config)._migration_status()
        assert status.head_revision == next_manifest.source_revision
        assert status.current_revision == doctor.source_revision
        assert status.state is RuntimeComponentState.DEGRADED
        assert status.reason_code is RuntimeDiagnosticCode.MIGRATION_NOT_CURRENT
    finally:
        database.close()
