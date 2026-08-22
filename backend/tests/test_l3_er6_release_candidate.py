from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app import models as _models  # noqa: F401 - register canonical metadata
from app.core import security
from app.runtime.desktop_sidecar import (
    _configure_embedded_release_candidate,
    _selected_generation,
)
from app.runtime.migrations.release_candidate import (
    BACKUP_MANIFEST_NAME,
    SYNTHETIC_FIXTURE_MARKER,
    ReleaseCandidateIntegrityError,
    ReleaseCandidateRestoreTargetError,
    ReleaseCandidateSyntheticOnlyError,
    RuntimeGenerationController,
    SyntheticReleaseCandidateBackup,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_database import (
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
)
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata

FIXED_NOW = datetime(2026, 8, 22, 5, 0, tzinfo=UTC)
GENERATION = "er6-roundtrip"
SYNTHETIC_SECRET = "er6-synthetic-app-secret"
SYNTHETIC_PROVIDER_CREDENTIAL = "-".join(("er6", "fixture", "credential"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_marker(
    root: Path,
    *,
    synthetic: bool = True,
    contains_real_credentials: bool = False,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / SYNTHETIC_FIXTURE_MARKER).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_id": "er6-two-world-roundtrip",
                "synthetic_fixture": synthetic,
                "contains_real_credentials": contains_real_credentials,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _seed_fixture(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[security.SecretScope, str]:
    _write_marker(root)
    secret_path = root / "secrets" / "app-secret"
    secret_path.parent.mkdir(parents=True)
    secret_path.write_text(SYNTHETIC_SECRET + "\n", encoding="utf-8")
    (root / "media" / "world-a").mkdir(parents=True)
    (root / "media" / "world-a" / "banner.png").write_bytes(
        b"synthetic-er6-banner"
    )
    (root / "graph" / "ladybug").mkdir(parents=True)
    (root / "graph" / "ladybug" / "replay.marker").write_text(
        "world-a:event-1\n",
        encoding="utf-8",
    )
    (root / "search").mkdir(parents=True)
    (root / "search" / "fts.digest").write_text("synthetic\n", encoding="utf-8")

    monkeypatch.setattr(
        security.settings,
        "APP_SECRET",
        type(security.settings.APP_SECRET)(SYNTHETIC_SECRET),
    )
    monkeypatch.setattr(security.settings, "APP_SECRET_FILE", None)
    monkeypatch.setattr(security.settings, "CREDENTIAL_ENCRYPTION_PROVIDER", "local")
    scope = security.SecretScope(
        owner_id="owner",
        character_id="mango",
        provider="gemini",
        purpose="agent",
    )
    envelope = security.encrypt_secret(SYNTHETIC_PROVIDER_CREDENTIAL, scope=scope)

    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(root),
        settings=SqliteCanonicalSettings(generation=GENERATION),
    )
    database.open()
    metadata = build_sqlite_baseline_metadata()
    with database.engine.begin() as connection:
        connection.execute(
            metadata.tables["users"].insert().values(
                id="owner",
                display_name="Synthetic Owner",
                display_name_normalized="synthetic owner",
                profile_setup_completed=True,
            )
        )
        connection.execute(
            metadata.tables["characters"].insert().values(
                id="mango",
                owner_id="owner",
                name="Mango",
                handle="mango-er6",
                one_liner="synthetic",
                personality="calm",
                speech_style="friendly",
                worldview="curious",
                topic_preferences="books",
                safety_rules="safe",
                status="active",
                moderation_status="active",
                execution_mode="llm",
                persona_summary="Synthetic Mango",
                created_at=FIXED_NOW,
            )
        )
        connection.execute(
            metadata.tables["llm_credentials"].insert().values(
                id="credential-er6",
                owner_id="owner",
                character_id="mango",
                provider="gemini",
                purpose="agent",
                model="gemini-fixture",
                auth_profile_id="er6-fixture",
                label="Synthetic key",
                encrypted_api_key=envelope,
                key_fingerprint="synthetic",
                enabled=True,
                created_at=FIXED_NOW,
                updated_at=FIXED_NOW,
            )
        )
    database.checkpoint(truncate=True)
    database.close()
    return scope, envelope


def test_synthetic_backup_restore_preserves_secret_and_local_v2_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "사용자 이름" / "Angmoo fixture"
    scope, envelope = _seed_fixture(source, monkeypatch)
    backup_root = tmp_path / "백업 경로" / "ER6 backup"
    restored_root = tmp_path / "복원 경로" / "ER6 restored"
    adapter = SyntheticReleaseCandidateBackup(
        data_paths=StaticRuntimeDataPath(source),
        app_version="0.4.0-1",
        now=lambda: FIXED_NOW,
    )

    created = adapter.create(backup_root)
    restored = adapter.restore(backup_root, restored_root)

    assert created.manifest.fixture_id == "er6-two-world-roundtrip"
    assert created.manifest.content_sha256 == restored.manifest.content_sha256
    assert (restored_root / BACKUP_MANIFEST_NAME).is_file()
    assert (restored_root / "media" / "world-a" / "banner.png").read_bytes() == (
        b"synthetic-er6-banner"
    )
    restored_secret = (
        restored_root / "secrets" / "app-secret"
    ).read_text(encoding="utf-8").strip()
    monkeypatch.setattr(
        security.settings,
        "APP_SECRET",
        type(security.settings.APP_SECRET)(restored_secret),
    )

    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(restored_root),
        settings=SqliteCanonicalSettings(generation=GENERATION),
    )
    database.open()
    metadata = build_sqlite_baseline_metadata()
    with database.engine.connect() as connection:
        restored_envelope = connection.execute(
            select(metadata.tables["llm_credentials"].c.encrypted_api_key).where(
                metadata.tables["llm_credentials"].c.id == "credential-er6"
            )
        ).scalar_one()
    database.close()
    assert restored_envelope == envelope
    assert (
        security.decrypt_secret(restored_envelope, scope=scope)
        == SYNTHETIC_PROVIDER_CREDENTIAL
    )


def test_backup_refuses_personal_or_real_credential_fixture(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    _write_marker(root, synthetic=False)
    adapter = SyntheticReleaseCandidateBackup(
        data_paths=StaticRuntimeDataPath(root),
        app_version="0.4.0-1",
    )
    with pytest.raises(
        ReleaseCandidateSyntheticOnlyError,
        match="personal_data_backup_refused",
    ):
        adapter.create(tmp_path / "personal-backup")

    _write_marker(root, contains_real_credentials=True)
    with pytest.raises(
        ReleaseCandidateSyntheticOnlyError,
        match="real_credential_backup_refused",
    ):
        adapter.create(tmp_path / "real-credential-backup")


def test_backup_detects_tamper_and_restore_requires_empty_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    _seed_fixture(root, monkeypatch)
    backup_root = tmp_path / "backup"
    adapter = SyntheticReleaseCandidateBackup(
        data_paths=StaticRuntimeDataPath(root),
        app_version="0.4.0-1",
    )
    adapter.create(backup_root)
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(
        ReleaseCandidateRestoreTargetError,
        match="restore_target_not_empty",
    ):
        adapter.restore(backup_root, occupied)

    (backup_root / "media" / "world-a" / "banner.png").write_bytes(b"tampered")
    with pytest.raises(
        ReleaseCandidateIntegrityError,
        match="backup_file_digest_mismatch",
    ):
        adapter.inspect(backup_root)


def test_generation_promote_and_rollback_are_atomic(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    data_paths = StaticRuntimeDataPath(root)
    databases: dict[str, Path] = {}
    for generation in ("generation-a", "generation-b"):
        database = SqliteCanonicalDatabase(
            data_paths,
            settings=SqliteCanonicalSettings(generation=generation),
        )
        database.open()
        database.checkpoint(truncate=True)
        database.close()
        databases[generation] = (
            root
            / "canonical"
            / "generations"
            / generation
            / "angmoo.sqlite3"
        )
    controller = RuntimeGenerationController(data_paths)

    first = controller.promote(
        "generation-a",
        content_sha256=_sha256(databases["generation-a"]),
    )
    second = controller.promote(
        "generation-b",
        content_sha256=_sha256(databases["generation-b"]),
    )
    rolled_back = controller.rollback()

    assert first["generation"] == "generation-a"
    assert second["generation"] == "generation-b"
    assert rolled_back["generation"] == "generation-a"
    assert controller.current() == first
    assert _selected_generation(root) == "generation-a"

    # A promoted canonical database changes during normal application use.
    # The marker digest attests the migration artifact, not the mutable DB file.
    databases["generation-a"].write_bytes(
        databases["generation-a"].read_bytes() + b"runtime-write-proof"
    )
    assert _selected_generation(root) == "generation-a"


def test_packaged_sidecar_creates_secret_once_and_reuses_it(
    tmp_path: Path,
) -> None:
    environment: dict[str, str] = {}
    runtime_root = tmp_path / "한글 사용자" / "Angmoo" / "runtime"
    runtime_root.mkdir(parents=True)
    first_root, first_generation = _configure_embedded_release_candidate(
        runtime_root,
        environ=environment,
    )
    secret_path = first_root / "secrets" / "app-secret"
    first_secret = secret_path.read_text(encoding="utf-8")

    second_root, second_generation = _configure_embedded_release_candidate(
        runtime_root,
        environ=environment,
    )

    assert second_root == first_root
    assert first_generation == second_generation == "er6-preview-v1"
    assert secret_path.read_text(encoding="utf-8") == first_secret
    assert Path(environment["APP_SECRET_FILE"]) == secret_path
    assert environment["APP_ENV"] == "local"
    assert environment["API_DOCS_ENABLED"] == "false"
    assert environment["SIGNUP_ENABLED"] == "false"
    assert environment["BROWSER_SESSION_ALLOWED_ORIGINS"] == (
        "http://tauri.localhost"
    )
