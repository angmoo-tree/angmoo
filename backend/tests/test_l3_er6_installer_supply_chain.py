from __future__ import annotations

import json
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPOSITORY_ROOT / "scripts" / "ci" / "build_desktop_release_metadata.py"
CONTRACT = REPOSITORY_ROOT / "scripts" / "ci" / "check_desktop_installer_contract.py"
VERSION = json.loads(
    (REPOSITORY_ROOT / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
)["version"]
INSTALLER_NAME = f"Angmoo_{VERSION}_x64-setup.exe"


def _run_generator(
    bundle: Path, output: Path, *, version: str | None = None, commit: str | None = None
) -> subprocess.CompletedProcess[str]:
    if commit is None:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT, text=True
        ).strip()
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--bundle-root",
            str(bundle),
            "--output-root",
            str(output),
            "--version",
            VERSION if version is None else version,
            "--commit",
            commit,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_installer_contract_checker_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CONTRACT)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "desktop-installer-contract: PASS" in result.stdout


@pytest.mark.parametrize("missing_resource_contract", (
    "--add-data $sqliteDeltaData",
    "$sqliteDeltaRoot\\*.json;app/runtime/migrations/sqlite_versions",
    '$sqliteDeltaRoot = Join-Path $backendRoot "app\\runtime\\migrations\\sqlite_versions"',
))
def test_installer_contract_rejects_missing_frozen_migration_resources(
    monkeypatch: pytest.MonkeyPatch,
    missing_resource_contract: str,
) -> None:
    spec = importlib.util.spec_from_file_location("installer_resource_contract", CONTRACT)
    assert spec is not None and spec.loader is not None
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    build = REPOSITORY_ROOT / "desktop/scripts/build-sidecar.ps1"
    read_text = Path.read_text

    def omit_resource(path: Path, *args, **kwargs):
        text = read_text(path, *args, **kwargs)
        if path == build:
            assert missing_resource_contract in text
            return text.replace(missing_resource_contract, "")
        return text

    monkeypatch.setattr(Path, "read_text", omit_resource)
    with pytest.raises(SystemExit, match="packaged embedded migration manifest missing"):
        contract.main()


def test_release_metadata_has_checksums_sbom_provenance_and_notices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = tmp_path / "bundle"
    output = tmp_path / "metadata"
    (bundle / "nsis").mkdir(parents=True)
    (bundle / "nsis" / INSTALLER_NAME).write_bytes(
        b"synthetic-nsis"
    )

    spec = importlib.util.spec_from_file_location('desktop_metadata_fixture', GENERATOR)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    resources = tmp_path / 'angmoo-resources.json'
    resource_data = {'fixture': 'synthetic-native-resources', 'files': {'bin/postgres.exe': 'a' * 64}}
    resources.write_text(json.dumps(resource_data), encoding='utf-8')
    monkeypatch.setattr(generator, '_postgresql_resource_manifest', lambda: resources)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPOSITORY_ROOT, text=True).strip()
    monkeypatch.setattr(sys, 'argv', [str(GENERATOR), '--bundle-root', str(bundle), '--output-root',
                                    str(output), '--version', VERSION, '--commit', commit])
    assert generator.main() == 0
    assert json.loads((output / 'postgresql-resources.json').read_text()) == resource_data
    sums = (output / "SHA256SUMS").read_text(encoding="ascii")
    assert INSTALLER_NAME in sums
    digest = hashlib.sha256(b"synthetic-nsis").hexdigest()
    assert sums == f"{digest}  {INSTALLER_NAME}\n"
    sbom = json.loads(
        (output / "angmoo-installer.spdx.json").read_text(encoding="utf-8")
    )
    assert sbom["spdxVersion"] == "SPDX-2.3"
    package_names = {package["name"] for package in sbom["packages"]}
    assert {"angmoo", "ladybug", "next", "tauri", "PostgreSQL", "pgvector-native"}.issubset(package_names)
    provenance = json.loads(
        (output / "angmoo-installer.provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["predicateType"] == "https://slsa.dev/provenance/v1"
    assert provenance["subject"] == [{
        "name": INSTALLER_NAME, "digest": {"sha256": digest}
    }]
    assert sbom["files"][0]["checksums"][0]["checksumValue"] == digest
    assert (output / "THIRD_PARTY_NOTICES.md").is_file()
    assert (output / "LICENSE").is_file()


def test_release_metadata_refuses_private_backup_payload(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    output = tmp_path / "metadata"
    bundle.mkdir()
    (bundle / "nsis").mkdir()
    (bundle / "nsis" / INSTALLER_NAME).write_bytes(b"synthetic-nsis")
    (bundle / "release-candidate-backup.json").write_text(
        "{}",
        encoding="utf-8",
    )

    result = _run_generator(bundle, output)

    assert result.returncode != 0
    assert "Private migration artifact refused" in result.stderr


@pytest.mark.parametrize("extra", (
    f"msi/Angmoo_{VERSION}_x64_en-US.msi",
    "msi/Angmoo_0.3.0_x64_en-US.msi",
    "nsis/Angmoo_0.3.0_x64-setup.exe",
    "nsis/angmoo-desktop.exe",
    f"nsis/Angmoo_{VERSION}_arm64-setup.exe",
    f"duplicate/{INSTALLER_NAME}",
    "nsis/extra.txt",
    "secrets/app-secret",
    "canonical/data.sqlite3",
    ".env",
))
def test_release_metadata_rejects_extra_stale_or_private_artifacts(
    tmp_path: Path, extra: str,
) -> None:
    bundle = tmp_path / "bundle"
    installer = bundle / "nsis" / INSTALLER_NAME
    installer.parent.mkdir(parents=True)
    installer.write_bytes(b"synthetic-nsis")
    forbidden = bundle / extra
    forbidden.parent.mkdir(parents=True, exist_ok=True)
    forbidden.write_bytes(b"must-not-publish")
    output = tmp_path / "metadata"
    result = _run_generator(bundle, output)
    assert result.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize("case", ("missing", "msi_only", "empty", "wrong_version", "wrong_source"))
def test_release_metadata_requires_current_installer_and_source(
    tmp_path: Path, case: str,
) -> None:
    bundle = tmp_path / "bundle"
    installer = bundle / "nsis" / INSTALLER_NAME
    installer.parent.mkdir(parents=True)
    version, commit = VERSION, None
    if case == "msi_only":
        (bundle / f"Angmoo_{VERSION}_x64.msi").write_bytes(b"synthetic-msi")
    elif case != "missing":
        installer.write_bytes(b"" if case == "empty" else b"synthetic-nsis")
    if case == "wrong_version":
        version = "0.0.0"
    elif case == "wrong_source":
        commit = "a" * 40
    output = tmp_path / "metadata"
    result = _run_generator(bundle, output, version=version, commit=commit)
    assert result.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize("setting", (
    "package", "npm_lock", "npm_lock_root", "cargo", "cargo_lock",
))
def test_release_metadata_rejects_inconsistent_desktop_product_versions(
    setting: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location("installer_version_contract", GENERATOR)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    owner = REPOSITORY_ROOT / "desktop"
    target = owner / {
        "package": "package.json", "npm_lock": "package-lock.json",
        "npm_lock_root": "package-lock.json", "cargo": "src-tauri/Cargo.toml",
        "cargo_lock": "src-tauri/Cargo.lock",
    }[setting]
    read_text = Path.read_text

    def version_drift(path: Path, *args, **kwargs):
        text = read_text(path, *args, **kwargs)
        if path != target:
            return text
        if setting in {"package", "npm_lock", "npm_lock_root"}:
            value = json.loads(text)
            if setting == "npm_lock_root":
                value["packages"][""]["version"] = "0.0.0"
            else:
                value["version"] = "0.0.0"
            return json.dumps(value)
        if setting == "cargo_lock":
            before = f'name = "angmoo-desktop"\nversion = "{VERSION}"'
            assert before in text
            return text.replace(before, 'name = "angmoo-desktop"\nversion = "0.0.0"', 1)
        return text.replace(f'version = "{VERSION}"', 'version = "0.0.0"', 1)

    monkeypatch.setattr(Path, "read_text", version_drift)
    with pytest.raises(SystemExit, match="Desktop product version settings disagree"):
        generator._source_identity(VERSION, "a" * 40)
