"""Inspect, back up, restore, and switch an ER6 synthetic fixture."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.runtime.migrations.release_candidate import (
    RuntimeGenerationController,
    SyntheticReleaseCandidateBackup,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage a synthetic ER6 installer migration fixture."
    )
    parser.add_argument(
        "command",
        choices=("backup", "inspect", "restore", "promote", "rollback"),
    )
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--target-root", type=Path)
    parser.add_argument("--app-version", default="0.4.0-1")
    parser.add_argument("--generation")
    parser.add_argument("--content-sha256")
    return parser


def main() -> int:
    args = _parser().parse_args()
    data_paths = StaticRuntimeDataPath(args.runtime_root)
    if args.command in {"backup", "inspect", "restore"}:
        if args.backup_root is None:
            raise SystemExit("--backup-root is required")
        backup = SyntheticReleaseCandidateBackup(
            data_paths=data_paths,
            app_version=args.app_version,
        )
        if args.command == "backup":
            report = backup.create(args.backup_root)
        elif args.command == "inspect":
            report = backup.inspect(args.backup_root)
        else:
            if args.target_root is None:
                raise SystemExit("--target-root is required for restore")
            report = backup.restore(args.backup_root, args.target_root)
        payload = {
            "backup_root": report.backup_root,
            "manifest": asdict(report.manifest),
        }
    else:
        controller = RuntimeGenerationController(data_paths)
        if args.command == "promote":
            if args.generation is None or args.content_sha256 is None:
                raise SystemExit("--generation and --content-sha256 are required")
            payload = controller.promote(
                args.generation,
                content_sha256=args.content_sha256,
            )
        else:
            payload = controller.rollback()
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
