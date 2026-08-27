"""Fail when a readable SQLite predecessor lacks a real NSIS fixture."""

from __future__ import annotations

from pathlib import Path
import sys


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


def main() -> int:
    manifest_versions = tuple(
        version
        for version in range(1, SQLITE_SCHEMA_VERSION + 1)
        if load_sqlite_manifest(version).schema_version == version
    )
    readable_predecessors = manifest_versions[:-1]
    if tuple(SUPPORTED_SOURCE_VERSIONS) != readable_predecessors:
        raise SystemExit(
            "windows_installer_supported_upgrade_matrix_incomplete:"
            f"expected={readable_predecessors}:"
            f"actual={tuple(SUPPORTED_SOURCE_VERSIONS)}"
        )
    print(
        "windows_installer_supported_upgrade_matrix_contract_pass:"
        + ",".join(f"v{version}" for version in readable_predecessors)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
