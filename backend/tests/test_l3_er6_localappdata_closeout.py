from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from app.runtime.migrations.local_app_data import LegacyLocalAppDataMigration

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.ci.build_er6_localappdata_lifecycle_fixture import build_fixture


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_synthetic_installed_fixture_migrates_and_preserves_product_data(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "사용자" / "com.angmoo.desktop"
    product = tmp_path / "사용자" / "Angmoo"
    manifest = build_fixture(legacy)

    report = LegacyLocalAppDataMigration(
        source_root=legacy,
        target_root=product,
        runtime_root=product / "runtime",
        process_alive=lambda _pid: False,
    ).migrate_if_needed()

    assert report.status == "migrated"
    assert report.generation == "er6-preview-v1"
    assert report.app_secret_sha256 == manifest["app_secret_sha256"]
    assert _sha256(product / "secrets" / "app-secret") == manifest[
        "app_secret_sha256"
    ]
    assert (legacy / "canonical").is_dir()
    assert not (product / "runtime" / "legacy-owner.lock").exists()
    assert not (product / "WebView2" / "Cookies").exists()

    database = (
        product
        / "canonical"
        / "generations"
        / "er6-preview-v1"
        / "angmoo.sqlite3"
    )
    with sqlite3.connect(database) as connection:
        for table, identifier in (
            ("users", "owner-er6"),
            ("worlds", "world-er6"),
            ("characters", "character-er6-mango"),
            ("world_characters", "world-character-er6-mango"),
            ("llm_credentials", "credential-er6-metadata"),
            ("posts", "post-er6-installed"),
        ):
            assert connection.execute(
                f'SELECT count(*) FROM "{table}" WHERE id = ?',
                (identifier,),
            ).fetchone() == (1,)

    second = LegacyLocalAppDataMigration(
        source_root=legacy,
        target_root=product,
        runtime_root=product / "runtime",
        process_alive=lambda _pid: False,
    ).migrate_if_needed()
    assert second.status == "already_migrated"


def test_fixture_is_explicitly_synthetic_and_refuses_occupied_output(
    tmp_path: Path,
) -> None:
    root = tmp_path / "fixture"
    manifest = build_fixture(root)
    on_disk = json.loads(
        (root / "fixture-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest == on_disk
    assert manifest["synthetic_fixture"] is True
    assert manifest["contains_real_credentials"] is False
    assert manifest["expected_ids"]["world"] == "world-er6"

    with pytest.raises(RuntimeError, match="fixture_output_root_not_empty"):
        build_fixture(root)
