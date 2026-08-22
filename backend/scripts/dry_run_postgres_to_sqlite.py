"""Run the production-OFF PostgreSQL to SQLite conversion proof."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
import sys

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import models as _models  # noqa: F401 - registers canonical metadata
from app.core.db import Base, engine
from app.runtime.migrations.alembic_source import AlembicMigrationSource
from app.runtime.migrations.postgres_to_sqlite import (
    PostgresToSqliteOfflineDryRun,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Copy one read-only PostgreSQL snapshot into a verified SQLite "
            "dry-run generation without switching production."
        )
    )
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--generation", required=True)
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--media-root", type=Path)
    parser.add_argument("--media-manifest", type=Path)
    parser.add_argument(
        "--confirm-source-stopped",
        action="store_true",
        help="Confirm the source application is stopped before taking the snapshot.",
    )
    parser.add_argument(
        "--minimum-free-gib",
        type=float,
        default=2.0,
        help="Fail before migration when the target volume has less free space.",
    )
    return parser


def _directory_bytes(root: Path | None) -> int:
    if root is None or not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _disk_preflight(args: argparse.Namespace) -> dict[str, int]:
    if engine.dialect.name != "postgresql":
        raise SystemExit("ER6 migration source must be PostgreSQL")
    with engine.connect() as connection:
        source_database_bytes = int(
            connection.scalar(text("SELECT pg_database_size(current_database())"))
            or 0
        )
    media_bytes = _directory_bytes(args.media_root)
    target_parent = args.output_root.resolve()
    while not target_parent.exists():
        target_parent = target_parent.parent
    free_bytes = shutil.disk_usage(target_parent).free
    minimum_bytes = max(0, int(args.minimum_free_gib * 1024**3))
    estimated_required_bytes = max(
        minimum_bytes,
        source_database_bytes * 2 + media_bytes + 512 * 1024**2,
    )
    if free_bytes < estimated_required_bytes:
        raise SystemExit(
            "migration_disk_preflight_failed "
            f"free_bytes={free_bytes} "
            f"estimated_required_bytes={estimated_required_bytes}"
        )
    return {
        "source_database_bytes": source_database_bytes,
        "media_bytes": media_bytes,
        "free_bytes": free_bytes,
        "estimated_required_bytes": estimated_required_bytes,
    }


def main() -> int:
    args = _parser().parse_args()
    if not args.confirm_source_stopped:
        raise SystemExit("--confirm-source-stopped is required")
    disk_preflight = _disk_preflight(args)
    migration = PostgresToSqliteOfflineDryRun(
        source_engine=engine,
        source_metadata=Base.metadata,
        data_paths=StaticRuntimeDataPath(args.output_root),
        migration_source=AlembicMigrationSource(
            BACKEND_ROOT / "app" / "alembic" / "versions"
        ),
        conversion_inventory_path=(
            REPOSITORY_ROOT
            / "docs"
            / "architecture"
            / "migration-conversion-inventory.json"
        ),
        generation=args.generation,
        app_version=args.app_version,
        media_root=args.media_root,
        media_manifest_path=args.media_manifest,
    )
    report = migration.dry_run()
    safe_report = {
        "manifest_version": report.manifest.manifest_version,
        "app_version": report.manifest.app_version,
        "source_dialect": report.manifest.source_dialect,
        "source_revision": report.manifest.source_revision,
        "source_migration_count": report.manifest.source_migration_count,
        "target_schema_version": report.manifest.target_schema_version,
        "table_count": len(report.manifest.tables),
        "content_sha256": report.manifest.content_sha256,
        "manifest_path": report.manifest_path,
        "target_database_path": report.target_database_path,
        "foreign_key_violation_count": report.foreign_key_violation_count,
        "integrity_check": report.integrity_check,
        "source_read_only": report.source_read_only,
        "production_switched": report.production_switched,
        "disk_preflight": disk_preflight,
    }
    print(
        json.dumps(
            safe_report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
