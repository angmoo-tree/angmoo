from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPOSITORY_ROOT / "scripts" / "ci" / "build_desktop_release_metadata.py"
CONTRACT = REPOSITORY_ROOT / "scripts" / "ci" / "check_desktop_installer_contract.py"


def _run_generator(bundle: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--bundle-root",
            str(bundle),
            "--output-root",
            str(output),
            "--version",
            "0.4.0-1",
            "--commit",
            "a" * 40,
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


def test_release_metadata_has_checksums_sbom_provenance_and_notices(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    output = tmp_path / "metadata"
    (bundle / "nsis").mkdir(parents=True)
    (bundle / "msi").mkdir(parents=True)
    (bundle / "nsis" / "Angmoo_0.4.0-1_x64-setup.exe").write_bytes(
        b"synthetic-nsis"
    )
    (bundle / "msi" / "Angmoo_0.4.0-1_x64_en-US.msi").write_bytes(
        b"synthetic-msi"
    )
    (bundle / "nsis" / "Angmoo_0.3.0_x64-setup.exe").write_bytes(b"stale")

    result = _run_generator(bundle, output)

    assert result.returncode == 0, result.stderr
    sums = (output / "SHA256SUMS").read_text(encoding="ascii")
    assert "Angmoo_0.4.0-1_x64-setup.exe" in sums
    assert "Angmoo_0.4.0-1_x64_en-US.msi" in sums
    assert "Angmoo_0.3.0_x64-setup.exe" not in sums
    sbom = json.loads(
        (output / "angmoo-installer.spdx.json").read_text(encoding="utf-8")
    )
    assert sbom["spdxVersion"] == "SPDX-2.3"
    package_names = {package["name"] for package in sbom["packages"]}
    assert {"angmoo", "ladybug", "next", "tauri"}.issubset(package_names)
    provenance = json.loads(
        (output / "angmoo-installer.provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["predicateType"] == "https://slsa.dev/provenance/v1"
    assert len(provenance["subject"]) == 2
    assert (output / "THIRD_PARTY_NOTICES.md").is_file()
    assert (output / "LICENSE").is_file()


def test_release_metadata_refuses_private_backup_payload(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    output = tmp_path / "metadata"
    bundle.mkdir()
    (bundle / "Angmoo_0.4.0-1_x64-setup.exe").write_bytes(b"synthetic-nsis")
    (bundle / "Angmoo_0.4.0-1_x64_en-US.msi").write_bytes(b"synthetic-msi")
    (bundle / "release-candidate-backup.json").write_text(
        "{}",
        encoding="utf-8",
    )

    result = _run_generator(bundle, output)

    assert result.returncode != 0
    assert "Private migration artifact refused" in result.stderr
