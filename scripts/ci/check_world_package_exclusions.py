#!/usr/bin/env python3
"""Run the World Package portable-data exclusion scanner."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.domains.world_packages.archive.exclusions import (
    WorldPackageExclusionError,
    scan_world_package_bytes,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that a .angmoo-world contains portable seed only."
    )
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    try:
        report = scan_world_package_bytes(args.package.read_bytes())
    except (OSError, WorldPackageExclusionError) as exc:
        print(f"world_package_exclusion_scan_failed:{type(exc).__name__}")
        return 1
    print(
        "world_package_exclusion_scan_passed:"
        f"entries={report.entry_count}:"
        f"json={report.json_document_count}:"
        f"bytes={report.scanned_uncompressed_bytes}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
