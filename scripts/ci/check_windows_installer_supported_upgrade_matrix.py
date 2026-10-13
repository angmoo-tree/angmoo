"""Fail when a readable SQLite predecessor lacks a real NSIS fixture."""

from __future__ import annotations

from pathlib import Path
import sys
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION
from build_windows_installer_supported_upgrade_fixture import (
    SUPPORTED_SOURCE_VERSIONS,
)


def validate_matrix(root: Path = REPOSITORY_ROOT) -> tuple[int, ...]:
    manifest_versions = tuple(
        version
        for version in range(1, SQLITE_SCHEMA_VERSION + 1)
        if load_sqlite_manifest(version).schema_version == version
    )
    readable_predecessors = manifest_versions[:-1]
    if tuple(SUPPORTED_SOURCE_VERSIONS) != readable_predecessors:
        raise ValueError(
            "windows_installer_supported_upgrade_matrix_incomplete:"
            f"expected={readable_predecessors}:"
            f"actual={tuple(SUPPORTED_SOURCE_VERSIONS)}"
        )
    workflow = (root / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    runner = (root / "scripts/ci/run_windows_installer_supported_upgrade.ps1").read_text(encoding="utf-8")
    jobs = yaml.safe_load(workflow)["jobs"]
    upgrade = jobs["windows-installer-supported-upgrade"]
    if (upgrade.get("strategy") != {"fail-fast": False, "matrix": {"partition": ["first", "second"]}}
            or upgrade.get("timeout-minutes") != 30 or "continue-on-error" in upgrade):
        raise ValueError("windows_installer_native_partitions_invalid")
    if not any("-UpgradePartition ${{ matrix.partition }}" in step.get("run", "")
               for step in upgrade["steps"]):
        raise ValueError("windows_installer_native_partition_not_executed")
    if not any("windows_installer_upgrade_coverage.py" in step.get("run", "")
               and '--run-attempt "$GITHUB_RUN_ATTEMPT"' in step["run"]
               for step in jobs["windows-installer"]["steps"]):
        raise ValueError("windows_installer_native_union_missing")
    for token in ("--select-partition $UpgradePartition", "foreach ($version in $selectedVersions)",
                  "Restore-IsolatedFixture $archive", "$supportedContract.source_data_version -ne [int]$version",
                  "$completedVersions.Add([int]$version)", "windows_installer_partition_coverage_incomplete"):
        if token not in runner:
            raise ValueError("windows_installer_dynamic_predecessor_execution_missing")
    if "build_installer_fixtures.py" not in workflow:
        raise ValueError("windows_installer_fixture_generation_missing")
    return readable_predecessors


def main() -> int:
    try:
        readable_predecessors = validate_matrix()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        "windows_installer_supported_upgrade_matrix_contract_pass:"
        + ",".join(f"v{version}" for version in readable_predecessors)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
