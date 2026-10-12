"""Startup migrations use the owned data root, never process credential settings."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3

from pydantic import SecretStr
import pytest

from app.config import settings
from app.core import security
from app.runtime.contributor_backend import _prepare_contributor_data_root
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeError
from app.runtime.migrations.generation import EmbeddedGenerationController
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest, SQLITE_SCHEMA_VERSION
from app.runtime.persistence.sqlite_schema import sqlite_schema_digest
from migrations.test_world_activity_v30 import populated_v29


def _seed_root(root: Path, monkeypatch, app_secret: str):
    root.mkdir()
    with monkeypatch.context() as seed_settings:
        seed_settings.setattr(settings, "APP_SECRET_FILE", None)
        seed_settings.setattr(settings, "APP_SECRET", SecretStr(app_secret))
        seed_settings.setattr(settings, "CREDENTIAL_ENCRYPTION_PROVIDER", "local")
        engine, *_ = populated_v29(root)
        manifest = load_sqlite_manifest(29)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO angmoo_schema_version VALUES (1,29,?,?,?,?)",
                (manifest.source_revision, manifest.source_migration_count,
                 sqlite_schema_digest(connection), datetime.now(UTC).isoformat()),
            )
        engine.dispose()
    database = root / "canonical/generations/fixture-v29/angmoo.sqlite3"
    database.parent.mkdir(parents=True)
    (root / "populated-v29.sqlite3").rename(database)
    secret = root / "secrets/app-secret"
    secret.parent.mkdir()
    secret.write_text(app_secret + "\n", encoding="utf-8")
    media = root / "media/fixture.txt"
    media.parent.mkdir()
    media.write_text("preserve original media", encoding="utf-8")
    controller = EmbeddedGenerationController(root / "canonical", artifact_relative_path="angmoo.sqlite3")
    controller.promote("generations/fixture-v29", manifest_sha256=manifest.manifest_sha256, data_version=29)
    return database, secret, media, controller


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_credentials(path):
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        return connection.execute(
            "SELECT purpose,provider,encrypted_secret,aad_character_id,aad_purpose "
            "FROM world_credentials ORDER BY purpose"
        ).fetchall()


def test_contributor_upgrade_authenticates_each_root_without_changing_process_settings(
    tmp_path, monkeypatch, deny_external_network,
):
    first = _seed_root(tmp_path / "first", monkeypatch, "first-owned-root-secret")
    second = _seed_root(tmp_path / "second", monkeypatch, "second-owned-root-secret")
    monkeypatch.setattr(settings, "APP_SECRET_FILE", str(tmp_path / "unrelated-missing-secret"))
    monkeypatch.setattr(settings, "APP_SECRET", SecretStr("unrelated-process-secret"))
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_PROVIDER", "oci_kms")
    original_settings = settings.model_dump()
    for database, secret, media, controller in (first, second):
        root = secret.parents[1]
        original = [_digest(p) for p in (database, secret, media)]
        result = _prepare_contributor_data_root(root)
        assert result.canonical.source_version == 29
        assert result.canonical.target_version == SQLITE_SCHEMA_VERSION
        assert [_digest(p) for p in (database, secret, media)] == original
        assert controller.current()["data_version"] == SQLITE_SCHEMA_VERSION
        credentials = _read_credentials(result.canonical.database_path)
        assert [r[0] for r in credentials] == ["image", "sns"]
        for credential_purpose, provider, envelope, character, purpose in credentials:
            raw = security.decrypt_local_secret(
                envelope, app_secret=secret.read_text(encoding="utf-8").strip(),
                scope=security.SecretScope(owner_id="consolidation-owner", character_id=character,
                                           provider=provider, purpose=purpose),
            )
            if credential_purpose == "image":
                # v35 deliberately retires the old general Comfy server key;
                # the original v29 DB/envelope and the Partner key stay intact.
                assert json.loads(raw) == {"version": "comfy-secrets.v1", "key": "",
                                           "partner": "synthetic-comfy-partner"}
            else:
                assert raw == "synthetic-sns-key"
        assert settings.model_dump() == original_settings
        again = _prepare_contributor_data_root(root)
        assert not again.canonical.migrated
        assert _read_credentials(again.canonical.database_path) == credentials
        assert settings.model_dump() == original_settings


def test_wrong_owned_secret_aborts_without_promoting_or_modifying_original_data(
    tmp_path, monkeypatch, deny_external_network,
):
    database, secret, media, controller = _seed_root(tmp_path / "data", monkeypatch, "original-owned-secret")
    secret.write_text("incorrect-owned-secret\n", encoding="utf-8")
    original = [_digest(p) for p in (database, secret, media, controller.current_marker)]
    original_settings = settings.model_dump()
    with pytest.raises(SqliteCanonicalUpgradeError, match="world_activity_secret_authentication_failed"):
        _prepare_contributor_data_root(secret.parents[1])
    assert [_digest(p) for p in (database, secret, media, controller.current_marker)] == original
    assert controller.current()["data_version"] == 29
    assert not list(controller.generations.glob(".*.tmp-*"))
    assert settings.model_dump() == original_settings
