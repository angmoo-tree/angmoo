"""Compare runtime diagnostics with the schema actually created by the product."""
from pathlib import Path

from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import text

from app.config import Settings
from app.domains.runtime.constants import RUNTIME_MIGRATION_HEAD, RuntimeDiagnosticCode
from app.domains.runtime.contracts.status import RuntimeComponentState
from app.runtime.diagnostics.status_composition import create_runtime_status_reader
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_database import SqliteCanonicalDatabase
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION, SOURCE_ALEMBIC_REVISION


def test_diagnostic_head_matches_shipped_sqlite_manifest_and_alembic_graph():
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic"))
    manifest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)
    assert RUNTIME_MIGRATION_HEAD == manifest.source_revision
    assert RUNTIME_MIGRATION_HEAD == SOURCE_ALEMBIC_REVISION
    assert scripts.get_heads() == [RUNTIME_MIGRATION_HEAD]


@pytest.mark.parametrize("replacement", [None, "20260825_0083", "20990101_9999"])
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
