"""Attested early-v28 recovery through the production copy/promotion boundary."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine

from app.runtime.migrations.embedded_sqlite import (
    SqliteCanonicalUpgradeCoordinator, SqliteCanonicalUpgradeError,
)
from app.runtime.migrations.generation import EmbeddedGenerationController
from app.runtime.migrations.sqlite_versions import registry, world_configuration_v28
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_schema import (
    SCHEMA_VERSION_TABLE, build_sqlite_v27_metadata, sqlite_schema_contract_digest,
    sqlite_schema_digest,
)
from world_configuration_fixture_support import seed_configuration_fixture


EARLY_MANIFEST_SHA256 = "8aa68a2a44e1d6eb40c7e312c55b889a7a0e26a2dca7e546e656b61fea5bf277"
EARLY_CONTRACT_SHA256 = "faa61f01f48468c507fe91069b562f019c42c0327e4fbdd8c6d94ed76a568262"


def _seed(root: Path, kind: str) -> Path:
    database = root / "canonical/generations/recovery-source/angmoo.sqlite3"
    database.parent.mkdir(parents=True)
    engine = seed_configuration_fixture(database, legacy=True)
    metadata = build_sqlite_v27_metadata()
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE world_characters SET autonomous_enabled=1, version=9 WHERE id='config-role-a'")
        connection.execute(metadata.tables["agent_runs"].insert().values(
            id="admitted-run", user_id="fixture-owner", character_id="config-actor-a",
            agent_id="admitted-slot", session_key="fixed-session", status="running",
            gateway_result={"accepted": {"persona": "Original accepted input"}},
        ))
        connection.execute(metadata.tables["agent_slots"].insert().values(
            agent_id="admitted-slot", assigned_user_id="fixture-owner",
            assigned_character_id="config-actor-a", assigned_credential_id="config-credential-a",
            status="running", locked_by_run_id="admitted-run",
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=10),
        ))
        if kind != "v27":
            world_configuration_v28.upgrade(connection)
            connection.exec_driver_sql(
                "UPDATE world_character_configurations SET settings=json_set(settings,'$.personality','Saved World A') "
                "WHERE world_character_id='config-role-a'"
            )
            connection.execute(metadata.tables["agent_creation_drafts"].insert().values(
                id="import-draft", user_id="fixture-owner", model="synthetic-model",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            ))
            connection.exec_driver_sql(
                "INSERT INTO character_draft_import_origins (draft_id,snapshot_id) "
                "SELECT 'import-draft',snapshot_id FROM character_import_origins WHERE character_id='config-actor-a'"
            )
            if kind == "early-v28":
                connection.exec_driver_sql("ALTER TABLE agent_runs DROP COLUMN input_snapshot")
                connection.exec_driver_sql("ALTER TABLE agent_slots DROP COLUMN admission_metadata")
                connection.exec_driver_sql("CREATE TEMP TABLE early_draft_origins AS SELECT * FROM character_draft_import_origins")
                connection.exec_driver_sql("DROP TABLE character_draft_import_origins")
                connection.exec_driver_sql("CREATE TABLE character_draft_import_origins (draft_id VARCHAR(64) NOT NULL, snapshot_id VARCHAR(36) NOT NULL, PRIMARY KEY (draft_id), FOREIGN KEY(draft_id) REFERENCES agent_creation_drafts (id), FOREIGN KEY(snapshot_id) REFERENCES character_import_snapshots (id))")
                connection.exec_driver_sql("INSERT INTO character_draft_import_origins SELECT * FROM early_draft_origins")
                connection.exec_driver_sql("DROP TABLE early_draft_origins")
            else:
                connection.exec_driver_sql("UPDATE agent_runs SET input_snapshot=?", (json.dumps({"fixed": "accepted persona", "revision": 7}),))
                connection.exec_driver_sql("UPDATE agent_slots SET admission_metadata=?", (json.dumps({"world": "config-world-a", "revision": 7}),))
        version = 27 if kind == "v27" else 28
        manifest = registry.load_sqlite_manifest(version, source_manifest_sha256=EARLY_MANIFEST_SHA256 if kind == "early-v28" else None)
        assert sqlite_schema_contract_digest(connection) == manifest.schema_digest
        connection.exec_driver_sql(
            f"INSERT INTO {SCHEMA_VERSION_TABLE} VALUES (1,?,?,?,?,?)",
            (version, manifest.source_revision, manifest.source_migration_count,
             sqlite_schema_digest(connection), "2026-10-05T10:14:39.383779Z"),
        )
    engine.dispose()
    EmbeddedGenerationController(root / "canonical", artifact_relative_path="angmoo.sqlite3").promote(
        "generations/recovery-source", manifest_sha256=manifest.manifest_sha256, data_version=version,
    )
    secret = root / "secrets/app-secret"
    secret.parent.mkdir()
    secret.write_text("synthetic-recovery-secret-only", encoding="utf-8")
    media = root / "media/preserved.txt"
    media.parent.mkdir()
    media.write_bytes(b"preserved-synthetic-media")
    return database


def _coordinator(root: Path) -> SqliteCanonicalUpgradeCoordinator:
    return SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(root), fallback_generation="recovery-source")


def _identity(path: Path, shape=None):
    engine = create_engine(f"sqlite:///{path}")
    result = {}
    with engine.connect() as connection:
        tables = [row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='angmoo_schema_version' ORDER BY name")]
        for table in tables:
            if shape is not None and table not in shape:
                continue
            columns = shape[table][0] if shape else tuple(row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")'))
            select = ",".join(f'"{column}"' for column in columns)
            result[table] = (columns, sorted([tuple(row) for row in connection.exec_driver_sql(f'SELECT {select} FROM "{table}"')], key=repr))
    engine.dispose()
    return result


@pytest.mark.parametrize("kind", ["v27", "early-v28", "final-v28"])
def test_production_upgrade_preserves_source_worlds_snapshots_and_admitted_work(tmp_path, kind):
    source = _seed(tmp_path, kind)
    before = _identity(source)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    marker = (tmp_path / "canonical/current-generation.json").read_bytes()
    result = _coordinator(tmp_path).upgrade()
    assert result.migrated and result.target_version == 29
    assert result.database_path != source
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha256
    assert (tmp_path / "canonical/previous-generation.json").read_bytes() == marker
    after = _identity(result.database_path, before)
    assert all(after[table] == value for table, value in before.items())
    engine = create_engine(f"sqlite:///{result.database_path}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert sqlite_schema_contract_digest(connection) == registry.load_sqlite_manifest(29).schema_digest
        fk = next(row for row in connection.exec_driver_sql("PRAGMA foreign_key_list(character_draft_import_origins)") if row[3] == "draft_id")
        assert fk[6] == "CASCADE"
        run_input = connection.exec_driver_sql("SELECT input_snapshot FROM agent_runs WHERE id='admitted-run'").scalar_one()
        slot_input = connection.exec_driver_sql("SELECT admission_metadata FROM agent_slots WHERE agent_id='admitted-slot'").scalar_one()
        if kind == "final-v28":
            assert json.loads(run_input) == {"fixed": "accepted persona", "revision": 7}
            assert json.loads(slot_input) == {"world": "config-world-a", "revision": 7}
        else:
            assert run_input is None and slot_input is None
    engine.dispose()
    current_marker = (tmp_path / "canonical/current-generation.json").read_bytes()
    promoted_identity = _identity(result.database_path)
    repeat = _coordinator(tmp_path).upgrade()
    assert not repeat.migrated and repeat.database_path == result.database_path
    assert (tmp_path / "canonical/current-generation.json").read_bytes() == current_marker
    assert _identity(repeat.database_path) == promoted_identity
    assert (tmp_path / "secrets/app-secret").read_text() == "synthetic-recovery-secret-only"
    assert (tmp_path / "media/preserved.txt").read_bytes() == b"preserved-synthetic-media"


@pytest.mark.parametrize("drift", ["extra-column", "missing-column", "raw-digest", "revision", "count", "marker", "foreign-key"])
def test_unattested_or_damaged_v28_is_rejected_without_promotion(tmp_path, drift):
    source = _seed(tmp_path, "early-v28")
    engine = create_engine(f"sqlite:///{source}")
    with engine.begin() as connection:
        if drift == "extra-column":
            connection.exec_driver_sql("ALTER TABLE agent_runs ADD COLUMN unknown_column TEXT")
        elif drift == "missing-column":
            connection.exec_driver_sql("ALTER TABLE agent_slots DROP COLUMN timezone_revision")
        elif drift == "raw-digest":
            connection.exec_driver_sql("UPDATE angmoo_schema_version SET schema_digest=?", ("0" * 64,))
        elif drift == "revision":
            connection.exec_driver_sql("UPDATE angmoo_schema_version SET source_revision='unattested'")
        elif drift == "count":
            connection.exec_driver_sql("UPDATE angmoo_schema_version SET source_migration_count=104")
        elif drift == "foreign-key":
            connection.exec_driver_sql("UPDATE character_draft_import_origins SET snapshot_id='missing-snapshot'")
        if drift in {"extra-column", "missing-column"}:
            connection.exec_driver_sql("UPDATE angmoo_schema_version SET schema_digest=?", (sqlite_schema_digest(connection),))
    engine.dispose()
    if drift == "marker":
        controller = EmbeddedGenerationController(tmp_path / "canonical", artifact_relative_path="angmoo.sqlite3")
        controller.promote("generations/recovery-source", manifest_sha256=registry.load_sqlite_manifest(28).manifest_sha256, data_version=28)
    marker = (tmp_path / "canonical/current-generation.json").read_bytes()
    before = source.read_bytes()
    with pytest.raises(SqliteCanonicalUpgradeError, match="sqlite_(schema_manifest_mismatch|foreign_key_check_failed)"):
        _coordinator(tmp_path).upgrade()
    assert source.read_bytes() == before
    assert (tmp_path / "canonical/current-generation.json").read_bytes() == marker
    assert list((tmp_path / "canonical/generations").iterdir()) == [source.parent]


def test_failed_staging_migration_keeps_source_and_can_resume(tmp_path, monkeypatch):
    source = _seed(tmp_path, "early-v28")
    before = source.read_bytes()
    marker = (tmp_path / "canonical/current-generation.json").read_bytes()
    original = registry.MIGRATIONS[28]
    def fail_after_repair(connection):
        original(connection)
        raise RuntimeError("controlled_failure_before_promotion")
    monkeypatch.setitem(registry.MIGRATIONS, 28, fail_after_repair)
    with pytest.raises(SqliteCanonicalUpgradeError, match="sqlite_migration_step_failed"):
        _coordinator(tmp_path).upgrade()
    assert source.read_bytes() == before
    assert (tmp_path / "canonical/current-generation.json").read_bytes() == marker
    assert list((tmp_path / "canonical/generations").iterdir()) == [source.parent]
    monkeypatch.setitem(registry.MIGRATIONS, 28, original)
    assert _coordinator(tmp_path).upgrade().target_version == 29


def test_semantic_delta_guard_rejects_rewritten_admitted_input(tmp_path, monkeypatch):
    source = _seed(tmp_path, "final-v28")
    before = source.read_bytes()
    original = registry.MIGRATIONS[28]
    def corrupt_input(connection):
        original(connection)
        connection.exec_driver_sql("UPDATE agent_runs SET input_snapshot='{}'")
    monkeypatch.setitem(registry.MIGRATIONS, 28, corrupt_input)
    with pytest.raises(SqliteCanonicalUpgradeError, match="world_configuration_v29_admitted_input_changed"):
        _coordinator(tmp_path).upgrade()
    assert source.read_bytes() == before
    assert list((tmp_path / "canonical/generations").iterdir()) == [source.parent]


def test_repaired_draft_foreign_key_cascades_without_deleting_basis(tmp_path):
    _seed(tmp_path, "early-v28")
    result = _coordinator(tmp_path).upgrade()
    engine = create_engine(f"sqlite:///{result.database_path}")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        before = connection.exec_driver_sql("SELECT count(*) FROM character_import_snapshots").scalar_one()
        connection.exec_driver_sql("DELETE FROM agent_creation_drafts WHERE id='import-draft'")
        assert connection.exec_driver_sql("SELECT count(*) FROM character_draft_import_origins").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT count(*) FROM character_import_snapshots").scalar_one() == before
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        connection.rollback()
    engine.dispose()


def test_contributor_factory_reopens_recovered_database_and_serves_health(tmp_path):
    from app.runtime.contributor_backend import create_contributor_runtime_app
    _seed(tmp_path, "early-v28")
    app = create_contributor_runtime_app(data_root=tmp_path)
    try:
        # Real synthetic lifecycle/HTTP; the admitted actor is busy and has
        # no usable provider key. The test process also blocks external I/O.
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200, response.json()
            assert response.json()["status"] == "ok"
            assert response.json()["persistence"] == "sqlite"
            assert response.json()["graph"] == "ladybug"
            with app.state.runtime_composition.session_factory() as session:
                from sqlalchemy import text
                assert session.execute(text("SELECT schema_version FROM angmoo_schema_version")).scalar_one() == 29
    finally:
        app.state.dispose_runtime()


def test_known_source_contract_does_not_replace_frozen_final_v28():
    final = registry.load_sqlite_manifest(28)
    early = registry.load_sqlite_manifest(28, source_manifest_sha256=EARLY_MANIFEST_SHA256)
    assert early.schema_digest == EARLY_CONTRACT_SHA256
    assert early.manifest_sha256 == EARLY_MANIFEST_SHA256
    assert final.schema_digest == "19263f9b90e8827364078a594f8466811e895cb6ce4396ab817dd8b9db5e23fa"
    assert final != early
    assert registry.load_sqlite_manifest(29).schema_digest == final.schema_digest
