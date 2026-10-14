from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from app.runtime import desktop_sidecar
from app.runtime.installer_update import (
    InstallerUpdateContractError,
    preflight_installer_embedded_data,
)
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION
from app.integrations.ladybug_projection import LADYBUG_PROJECTION_SCHEMA_VERSION


BUILD_COMMIT = "a" * 40
HOST_SHA = "b" * 64
SIDECAR_SHA = "c" * 64


def _manifest(path: Path, *, sqlite=(1, 8, 8), ladybug=(0, 2, 2)) -> Path:
    identity_source = "\n".join(
        (
            "0.4.0-1",
            BUILD_COMMIT,
            HOST_SHA,
            SIDECAR_SHA,
            f"sqlite:{sqlite[0]}-{sqlite[1]}->{sqlite[2]}",
            f"ladybug:{ladybug[0]}-{ladybug[1]}->{ladybug[2]}",
        )
    )
    payload = {
        "schema_version": 2,
        "product_version": "0.4.0-1",
        "build_commit": BUILD_COMMIT,
        "payload_generation": hashlib.sha256(
            identity_source.encode("utf-8")
        ).hexdigest(),
        "embedded_data": {
            "sqlite": {
                "minimum_readable_version": sqlite[0],
                "maximum_readable_version": sqlite[1],
                "target_version": sqlite[2],
            },
            "ladybug": {
                "minimum_readable_version": ladybug[0],
                "maximum_readable_version": ladybug[1],
                "target_version": ladybug[2],
            },
        },
        "files": {
            "angmoo-desktop.exe": HOST_SHA,
            "angmoo-sidecar.exe": SIDECAR_SHA,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _marker(root: Path, version: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "current-generation.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "relative_path": "generations/fixture",
                "manifest_sha256": "d" * 64,
                "data_version": version,
            }
        ),
        encoding="utf-8",
    )


def test_installer_preflight_accepts_supported_active_generations(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "Angmoo"
    _marker(data_root / "canonical", 1)
    _marker(data_root / "graph", 0)

    result = preflight_installer_embedded_data(
        data_root=data_root,
        payload_manifest=_manifest(tmp_path / "payload.json"),
    )

    assert result.sqlite_source_version == 1
    assert result.sqlite_target_version == 8
    assert result.ladybug_source_version == 0
    assert result.ladybug_target_version == 2


@pytest.mark.parametrize(
    ("sqlite_version", "ladybug_version", "expected"),
    (
        (9, 1, "installer_sqlite_data_incompatible"),
        (2, 3, "installer_ladybug_data_incompatible"),
    ),
)
def test_installer_preflight_blocks_incompatible_downgrade_without_mutation(
    tmp_path: Path,
    sqlite_version: int,
    ladybug_version: int,
    expected: str,
) -> None:
    data_root = tmp_path / "Angmoo"
    _marker(data_root / "canonical", sqlite_version)
    _marker(data_root / "graph", ladybug_version)
    before = {
        path: path.read_bytes()
        for path in data_root.rglob("current-generation.json")
    }

    with pytest.raises(InstallerUpdateContractError, match=expected):
        preflight_installer_embedded_data(
            data_root=data_root,
            payload_manifest=_manifest(tmp_path / "payload.json"),
        )

    assert {path: path.read_bytes() for path in before} == before


def test_installer_upgrade_mode_creates_current_generations_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_root = tmp_path / "Angmoo"
    manifest = _manifest(
        tmp_path / "payload.json",
        sqlite=(1, SQLITE_SCHEMA_VERSION, SQLITE_SCHEMA_VERSION),
        ladybug=(0, LADYBUG_PROJECTION_SCHEMA_VERSION, LADYBUG_PROJECTION_SCHEMA_VERSION),
    )
    argv = [
        "angmoo-sidecar",
        "--installer-data-upgrade",
        "--data-root",
        str(data_root),
        "--legacy-data-root",
        str(tmp_path / "legacy"),
        "--runtime-root",
        str(data_root / "runtime"),
        "--payload-manifest",
        str(manifest),
    ]
    monkeypatch.setattr(sys, "argv", argv)

    assert desktop_sidecar.main() == 0
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "upgraded"
    assert first["operation"] == "upgrade"
    result_path = (
        data_root / "runtime" / "installer-data-upgrade-result.json"
    )
    assert json.loads(result_path.read_text(encoding="utf-8")) == first
    assert first["sqlite_source_version"] is None
    assert first["ladybug_source_version"] is None
    canonical_marker = (
        data_root / "canonical" / "current-generation.json"
    ).read_bytes()
    graph_marker = (data_root / "graph" / "current-generation.json").read_bytes()

    marker_payload = json.loads(canonical_marker)
    database_path = (
        data_root
        / "canonical"
        / str(marker_payload["relative_path"])
        / "angmoo.sqlite3"
    )
    writer = sqlite3.connect(database_path)
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute(
            "UPDATE angmoo_schema_version SET created_at = ? "
            "WHERE singleton_key = 1",
            ("2026-08-27T00:00:00.000000Z",),
        )
        writer.commit()
        wal_path = database_path.with_name(database_path.name + "-wal")
        assert wal_path.is_file() and wal_path.stat().st_size > 0

        assert desktop_sidecar.main() == 0
        second = json.loads(capsys.readouterr().out)
        assert not wal_path.exists() or wal_path.stat().st_size == 0
    finally:
        writer.close()
    assert second["status"] == "upgraded"
    assert second["sqlite_source_version"] == SQLITE_SCHEMA_VERSION
    assert second["ladybug_source_version"] == LADYBUG_PROJECTION_SCHEMA_VERSION
    assert (data_root / "canonical" / "current-generation.json").read_bytes() == canonical_marker
    assert (data_root / "graph" / "current-generation.json").read_bytes() == graph_marker


def test_installer_failure_writes_one_redacted_stable_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "Angmoo"
    _marker(data_root / "canonical", 9)
    _marker(data_root / "graph", 1)
    result_path = data_root / "runtime" / "installer-result.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "angmoo-sidecar",
            "--installer-data-preflight",
            "--data-root",
            str(data_root),
            "--legacy-data-root",
            str(tmp_path / "legacy"),
            "--runtime-root",
            str(data_root / "runtime"),
            "--payload-manifest",
            str(_manifest(tmp_path / "payload.json")),
            "--installer-result-path",
            str(result_path),
        ],
    )

    with pytest.raises(
        InstallerUpdateContractError,
        match="installer_sqlite_data_incompatible",
    ):
        desktop_sidecar.main()

    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "status": "failed",
        "operation": "preflight",
        "code": "installer_sqlite_data_incompatible",
    }


def test_installer_upgrade_failure_reports_source_and_unchanged_active_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "Angmoo"
    _marker(data_root / "canonical", 2)
    _marker(data_root / "graph", 1)
    result_path = data_root / "runtime" / "installer-result.json"
    manifest = _manifest(tmp_path / "payload.json")
    payload_generation = json.loads(manifest.read_text(encoding="utf-8"))[
        "payload_generation"
    ]
    monkeypatch.setattr(
        desktop_sidecar,
        "_build_embedded_runtime_config",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("sqlite_migration_expected_delta_mismatch")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "angmoo-sidecar",
            "--installer-data-upgrade",
            "--data-root",
            str(data_root),
            "--legacy-data-root",
            str(tmp_path / "legacy"),
            "--runtime-root",
            str(data_root / "runtime"),
            "--payload-manifest",
            str(manifest),
            "--installer-result-path",
            str(result_path),
        ],
    )

    with pytest.raises(
        RuntimeError,
        match="sqlite_migration_expected_delta_mismatch",
    ):
        desktop_sidecar.main()

    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result == {
        "schema_version": 1,
        "status": "failed",
        "operation": "upgrade",
        "code": "sqlite_migration_expected_delta_mismatch",
        "build_commit": BUILD_COMMIT,
        "payload_generation": payload_generation,
        "sqlite_source_version": 2,
        "sqlite_target_version": 8,
        "sqlite_active_version": 2,
        "ladybug_source_version": 1,
        "ladybug_target_version": 2,
        "ladybug_active_version": 1,
    }


def test_installer_mode_fatal_code_is_stable() -> None:
    assert (
        desktop_sidecar._stable_fatal_code(
            InstallerUpdateContractError("installer_sqlite_data_incompatible")
        )
        == "installer_sqlite_data_incompatible"
    )


class _InvalidConsole:
    def __init__(self, *, fail_on_flush: bool = False) -> None:
        self.fail_on_flush = fail_on_flush
        self.output = ""

    def write(self, value: str) -> int:
        if not self.fail_on_flush:
            raise OSError(22, "Invalid argument")
        self.output += value
        return len(value)

    def flush(self) -> None:
        raise OSError(22, "Invalid argument")


@pytest.mark.parametrize("console_state", ("absent", "closed", "write", "flush"))
def test_process_failure_exits_nonzero_even_when_console_is_unusable(
    console_state: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = None
    if console_state == "closed":
        stream = io.StringIO()
        stream.close()
    elif console_state in {"write", "flush"}:
        stream = _InvalidConsole(fail_on_flush=console_state == "flush")

    def fail() -> int:
        raise RuntimeError("installer_result_path_outside_runtime_root")

    monkeypatch.setattr(desktop_sidecar, "main", fail)
    with monkeypatch.context() as context:
        context.setattr(sys, "stderr", stream)
        assert desktop_sidecar._run_process() == 1


def test_process_failure_emits_only_stable_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.StringIO()

    def fail() -> int:
        raise RuntimeError("private fixture text must not be disclosed")

    monkeypatch.setattr(desktop_sidecar, "main", fail)
    with monkeypatch.context() as context:
        context.setattr(sys, "stderr", stream)
        assert desktop_sidecar._run_process() == 1
    assert json.loads(stream.getvalue()) == {
        "event": "fatal",
        "code": "desktop_sidecar_startup_failed",
    }


@pytest.mark.parametrize("console_state", ("absent", "closed", "write", "flush"))
def test_preflight_durable_result_survives_unusable_console(
    console_state: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "Angmoo"
    result_path = data_root / "runtime" / "installer-result.json"
    monkeypatch.setattr(sys, "argv", [
        "angmoo-sidecar", "--installer-data-preflight",
        "--data-root", str(data_root),
        "--legacy-data-root", str(tmp_path / "legacy"),
        "--runtime-root", str(data_root / "runtime"),
        "--payload-manifest", str(_manifest(tmp_path / "payload.json")),
        "--installer-result-path", str(result_path),
    ])
    stream = None
    if console_state == "closed":
        stream = io.StringIO()
        stream.close()
    elif console_state in {"write", "flush"}:
        stream = _InvalidConsole(fail_on_flush=console_state == "flush")
    with monkeypatch.context() as context:
        context.setattr(sys, "stdout", stream)
        assert desktop_sidecar._run_installer_mode() == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "compatible"
    assert result["operation"] == "preflight"
    assert result["build_commit"] == BUILD_COMMIT


def test_preflight_rejects_result_outside_runtime_before_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "Angmoo"
    result_path = tmp_path / "forbidden-result.json"
    monkeypatch.setattr(sys, "argv", [
        "angmoo-sidecar", "--installer-data-preflight",
        "--data-root", str(data_root),
        "--legacy-data-root", str(tmp_path / "legacy"),
        "--runtime-root", str(data_root / "runtime"),
        "--payload-manifest", str(tmp_path / "unused-payload.json"),
        "--installer-result-path", str(result_path),
    ])

    def unexpected_operation(*args, **kwargs):
        pytest.fail("An unsafe result path must be rejected before data preparation")

    monkeypatch.setattr(desktop_sidecar, "_run_installer_operation", unexpected_operation)
    assert desktop_sidecar._run_process() == 1
    assert not result_path.exists()
    assert not data_root.exists()
