from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest

from app.runtime.migrations.local_app_data import (
    LegacyLocalAppDataMigration,
    LocalAppDataMigrationConflict,
    LocalAppDataMigrationError,
    LocalAppDataMigrationIntegrityError,
    MIGRATION_LOCK_NAME,
    MIGRATION_MARKER_NAME,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_database import (
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
)
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION


def test_localappdata_import_does_not_initialize_postgres_runtime() -> None:
    script = """
import sys
import app.runtime.migrations.local_app_data
assert 'app.runtime.migrations.postgres_to_sqlite' not in sys.modules
assert 'app.core.db' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _preview_fixture(root: Path) -> dict[str, str]:
    # The installed sidecar imports the public composition root before it
    # initializes SQLite. Mirror that explicit model-registration boundary;
    # the migrations package must not provide it as an accidental side effect.
    import_module("app.public_main")
    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(root),
        settings=SqliteCanonicalSettings(generation="er6-preview-v1"),
    )
    database.open()
    database.close()
    files = {
        "secrets/app-secret": "fixture-secret-not-a-real-key\n",
        "media/world/banner.txt": "media-proof",
        "graph/ladybug/catalog.txt": "graph-proof",
        "search/fts-rebuild.txt": "search-proof",
        "runtime/stale-owner.json": "must-not-migrate",
        "WebView2/Cookies": "must-reconnect-not-copy",
    }
    for relative, value in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    return files


def _migration(source: Path, target: Path, *, alive: bool = False):
    return LegacyLocalAppDataMigration(
        source_root=source,
        target_root=target,
        runtime_root=target / "runtime",
        process_alive=lambda _pid: alive,
    )


def test_preview_data_migrates_once_with_hash_and_schema_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "Angmoo"
    _preview_fixture(source)
    for name in (
        "canonical",
        "graph",
        "search",
        "media",
        "secrets",
        "runtime",
        "logs",
        "webview",
    ):
        (target / name).mkdir(parents=True)

    first = _migration(source, target).migrate_if_needed()

    assert first.status == "migrated"
    assert first.generation == "er6-preview-v1"
    assert first.schema_version == SQLITE_SCHEMA_VERSION
    assert first.canonical_table_count is not None
    assert first.canonical_table_count > 0
    assert first.copied_file_count >= 5
    assert len(first.copied_content_sha256 or "") == 64
    assert first.app_secret_sha256 == _sha256(
        source / "secrets" / "app-secret"
    )
    assert (target / "canonical" / "generations").is_dir()
    assert (target / "graph" / "ladybug" / "catalog.txt").is_file()
    assert (target / "search" / "fts-rebuild.txt").is_file()
    assert (target / "media" / "world" / "banner.txt").is_file()
    assert not (target / "runtime" / "stale-owner.json").exists()
    assert not (target / "WebView2").exists()
    assert json.loads(
        (target / MIGRATION_MARKER_NAME).read_text(encoding="utf-8")
    )["webview_policy"] == "product_profile_reconnect"
    # The source remains an intact rollback candidate until ER6 closeout.
    assert (source / "canonical" / "generations").is_dir()

    (target / "media" / "runtime-write.txt").write_text(
        "legitimate post-migration write",
        encoding="utf-8",
    )
    second = _migration(source, target).migrate_if_needed()
    assert second.status == "already_migrated"


def test_migration_fails_closed_when_both_roots_have_data(tmp_path: Path) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "Angmoo"
    _preview_fixture(source)
    (target / "canonical").mkdir(parents=True)
    (target / "canonical" / "unexpected.sqlite3").write_bytes(b"new-data")

    with pytest.raises(
        LocalAppDataMigrationConflict,
        match="legacy_and_product_data_conflict",
    ):
        _migration(source, target).migrate_if_needed()

    assert not (target / MIGRATION_MARKER_NAME).exists()
    assert (source / "secrets" / "app-secret").is_file()


def test_preview_data_and_launcher_dpapi_secrets_are_synthesized(
    tmp_path: Path,
) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "angmoo"
    _preview_fixture(source)
    launcher_secrets = {
        "app-secret.dpapi": b"synthetic-launcher-app-secret-dpapi",
        "neo4j-local-password.dpapi": b"synthetic-neo4j-password-dpapi",
    }
    for name, value in launcher_secrets.items():
        path = target / "secrets" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    original_hashes = {
        name: _sha256(target / "secrets" / name)
        for name in launcher_secrets
    }

    report = _migration(source, target).migrate_if_needed()

    assert report.status == "migrated"
    assert (target / "secrets" / "app-secret").is_file()
    for name, expected_hash in original_hashes.items():
        assert _sha256(target / "secrets" / name) == expected_hash
        assert not (source / "secrets" / name).exists()
    assert report.copied_file_count >= 7
    assert json.loads(
        (target / MIGRATION_MARKER_NAME).read_text(encoding="utf-8")
    )["copied_file_count"] == report.copied_file_count


def test_synthesized_migration_still_rejects_unknown_product_secret(
    tmp_path: Path,
) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "Angmoo"
    _preview_fixture(source)
    unknown = target / "secrets" / "unexpected-secret"
    unknown.parent.mkdir(parents=True)
    unknown.write_text("must-not-merge", encoding="utf-8")

    with pytest.raises(
        LocalAppDataMigrationConflict,
        match="legacy_and_product_data_conflict",
    ):
        _migration(source, target).migrate_if_needed()

    assert unknown.read_text(encoding="utf-8") == "must-not-merge"
    assert not (target / MIGRATION_MARKER_NAME).exists()
    assert (source / "secrets" / "app-secret").is_file()


def test_synthesized_migration_failure_preserves_launcher_dpapi_secret(
    tmp_path: Path,
) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "angmoo"
    _preview_fixture(source)
    database = (
        source
        / "canonical"
        / "generations"
        / "er6-preview-v1"
        / "angmoo.sqlite3"
    )
    database.write_bytes(b"not-sqlite")
    dpapi = target / "secrets" / "app-secret.dpapi"
    dpapi.parent.mkdir(parents=True)
    dpapi.write_bytes(b"synthetic-launcher-app-secret-dpapi")
    expected_hash = _sha256(dpapi)

    with pytest.raises(
        LocalAppDataMigrationIntegrityError,
        match="legacy_migration_canonical_invalid",
    ):
        _migration(source, target).migrate_if_needed()

    assert _sha256(dpapi) == expected_hash
    assert not (target / "secrets" / "app-secret").exists()
    assert not (target / MIGRATION_MARKER_NAME).exists()


def test_corrupt_canonical_rolls_back_without_touching_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "Angmoo"
    _preview_fixture(source)
    database = (
        source
        / "canonical"
        / "generations"
        / "er6-preview-v1"
        / "angmoo.sqlite3"
    )
    database.write_bytes(b"not-sqlite")
    (target / "runtime").mkdir(parents=True)

    with pytest.raises(
        LocalAppDataMigrationIntegrityError,
        match="legacy_migration_canonical_invalid",
    ):
        _migration(source, target).migrate_if_needed()

    assert database.read_bytes() == b"not-sqlite"
    assert not (target / MIGRATION_MARKER_NAME).exists()
    assert not any((target / name).exists() for name in ("canonical", "graph"))


def test_stale_lock_is_replaced_but_live_lock_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "Angmoo"
    _preview_fixture(source)
    runtime = target / "runtime"
    runtime.mkdir(parents=True)
    lock = runtime / MIGRATION_LOCK_NAME
    lock.write_text(
        json.dumps({"schema_version": 1, "pid": 2_147_483_647}),
        encoding="utf-8",
    )

    assert _migration(source, target).migrate_if_needed().status == "migrated"
    assert not lock.exists()

    second_source = tmp_path / "legacy-second"
    second_target = tmp_path / "product-second"
    _preview_fixture(second_source)
    (second_target / "runtime").mkdir(parents=True)
    (second_target / "runtime" / MIGRATION_LOCK_NAME).write_text(
        json.dumps({"schema_version": 1, "pid": 42}),
        encoding="utf-8",
    )
    with pytest.raises(LocalAppDataMigrationError, match="legacy_migration_locked"):
        _migration(second_source, second_target, alive=True).migrate_if_needed()


def test_completed_marker_cannot_be_reused_for_another_product_root(
    tmp_path: Path,
) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "Angmoo"
    _preview_fixture(source)
    report = _migration(source, target).migrate_if_needed()
    marker_path = target / MIGRATION_MARKER_NAME
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["target_root"] = str(tmp_path / "DifferentProduct")
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(
        LocalAppDataMigrationIntegrityError,
        match="legacy_migration_marker_root_mismatch",
    ):
        _migration(source, target).migrate_if_needed()

    assert report.status == "migrated"


def test_runtime_root_must_be_the_product_owned_runtime_directory(
    tmp_path: Path,
) -> None:
    migration = LegacyLocalAppDataMigration(
        source_root=tmp_path / "legacy",
        target_root=tmp_path / "Angmoo",
        runtime_root=tmp_path / "elsewhere",
        process_alive=lambda _pid: False,
    )
    with pytest.raises(
        LocalAppDataMigrationError,
        match="migration_runtime_root_outside_product_root",
    ):
        migration.migrate_if_needed()
