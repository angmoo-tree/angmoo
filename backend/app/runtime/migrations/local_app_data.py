"""Fail-closed migration from the ER6 preview data root to the product root."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from uuid import uuid4

MIGRATION_MARKER_NAME = "localappdata-migration-v1.json"
MIGRATION_LOCK_NAME = "localappdata-migration-v1.lock"
_PERSISTENT_DIRECTORIES = (
    "canonical",
    "graph",
    "search",
    "media",
    "secrets",
)


class LocalAppDataMigrationError(RuntimeError):
    pass


class LocalAppDataMigrationConflict(LocalAppDataMigrationError):
    pass


class LocalAppDataMigrationIntegrityError(LocalAppDataMigrationError):
    pass


@dataclass(frozen=True)
class LocalAppDataMigrationReport:
    status: str
    source_root: str
    target_root: str
    generation: str | None
    schema_version: int | None
    source_revision: str | None
    canonical_table_count: int | None
    copied_file_count: int
    copied_content_sha256: str | None
    app_secret_sha256: str | None
    webview_policy: str


class LegacyLocalAppDataMigration:
    """Copy verified product data while leaving the preview source intact."""

    def __init__(
        self,
        *,
        source_root: Path,
        target_root: Path,
        runtime_root: Path,
        process_alive: Callable[[int], bool],
    ) -> None:
        self.source_root = source_root.resolve()
        self.target_root = target_root.resolve()
        self.runtime_root = runtime_root.resolve()
        self._process_alive = process_alive
        self.marker_path = self.target_root / MIGRATION_MARKER_NAME
        self.lock_path = self.runtime_root / MIGRATION_LOCK_NAME

    def migrate_if_needed(self) -> LocalAppDataMigrationReport:
        self._validate_roots()
        completed = self._completed_report()
        if completed is not None:
            return completed
        if not _contains_persistent_data(self.source_root):
            return LocalAppDataMigrationReport(
                status="not_required",
                source_root=str(self.source_root),
                target_root=str(self.target_root),
                generation=None,
                schema_version=None,
                source_revision=None,
                canonical_table_count=None,
                copied_file_count=0,
                copied_content_sha256=None,
                app_secret_sha256=None,
                webview_policy="product_profile_fresh_or_reconnect",
            )
        if _contains_persistent_data(self.target_root):
            raise LocalAppDataMigrationConflict(
                "legacy_and_product_data_conflict"
            )

        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self._acquire_lock()
        staging = self.target_root / f".migration-{uuid4().hex}"
        installed: list[Path] = []
        try:
            staging.mkdir(parents=True)
            for name in _PERSISTENT_DIRECTORIES:
                source = self.source_root / name
                if source.exists():
                    _copy_tree_without_links(source, staging / name)

            source_summary = _file_summary(self.source_root)
            staged_summary = _file_summary(staging)
            if source_summary != staged_summary:
                raise LocalAppDataMigrationIntegrityError(
                    "legacy_migration_staging_digest_mismatch"
                )
            doctor = _validate_staged_canonical(staging)

            for name in _PERSISTENT_DIRECTORIES:
                staged = staging / name
                if not staged.exists():
                    continue
                destination = self.target_root / name
                if destination.exists():
                    if any(destination.iterdir()):
                        raise LocalAppDataMigrationConflict(
                            "legacy_and_product_data_conflict"
                        )
                    destination.rmdir()
                staged.replace(destination)
                installed.append(destination)

            installed_summary = _file_summary(self.target_root)
            if installed_summary != source_summary:
                raise LocalAppDataMigrationIntegrityError(
                    "legacy_migration_installed_digest_mismatch"
                )
            report = LocalAppDataMigrationReport(
                status="migrated",
                source_root=str(self.source_root),
                target_root=str(self.target_root),
                generation=doctor["generation"],
                schema_version=doctor["schema_version"],
                source_revision=doctor["source_revision"],
                canonical_table_count=doctor["canonical_table_count"],
                copied_file_count=len(installed_summary),
                copied_content_sha256=_content_sha256(installed_summary),
                app_secret_sha256=installed_summary.get(
                    "secrets/app-secret"
                ),
                # WebView2 is already live by the time the sidecar starts. We
                # intentionally use the new product profile and allow owner
                # bootstrap to reconnect from canonical identity state.
                webview_policy="product_profile_reconnect",
            )
            _write_json_atomic(self.marker_path, asdict(report))
            return report
        except BaseException:
            for destination in reversed(installed):
                shutil.rmtree(destination, ignore_errors=True)
                destination.mkdir(parents=True, exist_ok=True)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            self.lock_path.unlink(missing_ok=True)

    def _validate_roots(self) -> None:
        if self.source_root == self.target_root:
            raise LocalAppDataMigrationError("legacy_source_equals_product_root")
        if self.runtime_root != self.target_root / "runtime":
            raise LocalAppDataMigrationError(
                "migration_runtime_root_outside_product_root"
            )
        if self.source_root in self.target_root.parents:
            raise LocalAppDataMigrationError("product_root_inside_legacy_source")
        if self.target_root in self.source_root.parents:
            raise LocalAppDataMigrationError("legacy_source_inside_product_root")

    def _completed_report(self) -> LocalAppDataMigrationReport | None:
        if not self.marker_path.is_file():
            return None
        try:
            payload = json.loads(self.marker_path.read_text(encoding="utf-8"))
            report = LocalAppDataMigrationReport(**payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
            raise LocalAppDataMigrationIntegrityError(
                "legacy_migration_marker_invalid"
            ) from exc
        if report.status != "migrated":
            raise LocalAppDataMigrationIntegrityError(
                "legacy_migration_marker_invalid"
            )
        if (
            Path(report.source_root).resolve() != self.source_root
            or Path(report.target_root).resolve() != self.target_root
        ):
            raise LocalAppDataMigrationIntegrityError(
                "legacy_migration_marker_root_mismatch"
            )
        doctor = _validate_staged_canonical(self.target_root)
        if (
            doctor["generation"] != report.generation
            or doctor["schema_version"] != report.schema_version
            or doctor["source_revision"] != report.source_revision
            or doctor["canonical_table_count"]
            != report.canonical_table_count
        ):
            raise LocalAppDataMigrationIntegrityError(
                "legacy_migration_marker_canonical_mismatch"
            )
        if report.app_secret_sha256 is not None:
            secret_path = self.target_root / "secrets" / "app-secret"
            if not secret_path.is_file() or _sha256(secret_path) != report.app_secret_sha256:
                raise LocalAppDataMigrationIntegrityError(
                    "legacy_migration_marker_secret_mismatch"
                )
        return LocalAppDataMigrationReport(**{**asdict(report), "status": "already_migrated"})

    def _acquire_lock(self) -> None:
        if self.lock_path.exists():
            try:
                payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
                owner_pid = int(payload["pid"])
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                owner_pid = 0
            if owner_pid > 0 and self._process_alive(owner_pid):
                raise LocalAppDataMigrationError("legacy_migration_locked")
            self.lock_path.unlink(missing_ok=True)
        descriptor = os.open(
            self.lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"schema_version": 1, "pid": os.getpid()}, stream)


def _contains_persistent_data(root: Path) -> bool:
    return any(
        directory.exists() and any(directory.rglob("*"))
        for directory in (root / name for name in _PERSISTENT_DIRECTORIES)
    )


def _copy_tree_without_links(source: Path, target: Path) -> None:
    if source.is_symlink():
        raise LocalAppDataMigrationIntegrityError(
            "legacy_migration_link_not_allowed"
        )
    target.mkdir(parents=True)
    for child in source.iterdir():
        if child.is_symlink():
            raise LocalAppDataMigrationIntegrityError(
                "legacy_migration_link_not_allowed"
            )
        destination = target / child.name
        if child.is_dir():
            _copy_tree_without_links(child, destination)
        elif child.is_file():
            shutil.copy2(child, destination)
        else:
            raise LocalAppDataMigrationIntegrityError(
                "legacy_migration_unsupported_file"
            )


def _file_summary(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in _PERSISTENT_DIRECTORIES:
        directory = root / name
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise LocalAppDataMigrationIntegrityError(
                    "legacy_migration_link_not_allowed"
                )
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            result[relative] = _sha256(path)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_sha256(summary: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for path, file_digest in sorted(summary.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _validate_staged_canonical(staging: Path) -> dict[str, Any]:
    marker_path = staging / "canonical" / "current-generation.json"
    if marker_path.is_file():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            generation = str(marker["generation"])
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as exc:
            raise LocalAppDataMigrationIntegrityError(
                "legacy_migration_generation_marker_invalid"
            ) from exc
    else:
        # The first ER6 preview shipped before the generation marker became a
        # first-run requirement. Its sidecar deterministically selected this
        # generation name, so it is the only markerless layout we accept.
        generation = "er6-preview-v1"
    database_path = (
        staging / "canonical" / "generations" / generation / "angmoo.sqlite3"
    )
    if not database_path.is_file():
        raise LocalAppDataMigrationIntegrityError(
            "legacy_migration_generation_database_missing"
        )
    try:
        # `mode=ro` alone can still materialize a WAL shared-memory sidecar on
        # Windows.  The source runtime is offline at this gate and its copied
        # database must be byte-for-byte immutable while we validate it.
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro&immutable=1",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise LocalAppDataMigrationIntegrityError(
                "legacy_migration_canonical_integrity_failed"
            )
        schema = connection.execute(
            """
            SELECT schema_version, source_revision
            FROM angmoo_schema_version
            WHERE singleton_key = 1
            """
        ).fetchone()
        if schema is None:
            raise LocalAppDataMigrationIntegrityError(
                "legacy_migration_schema_marker_missing"
            )
        canonical_table_count = int(
            connection.execute(
                """
                SELECT count(*) FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                  AND name != 'angmoo_schema_version'
                """
            ).fetchone()[0]
        )
        return {
            "generation": generation,
            "schema_version": int(schema["schema_version"]),
            "source_revision": str(schema["source_revision"]),
            "canonical_table_count": canonical_table_count,
        }
    except Exception as exc:
        raise LocalAppDataMigrationIntegrityError(
            "legacy_migration_canonical_invalid"
        ) from exc
    finally:
        if "connection" in locals():
            connection.close()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


__all__ = [
    "LegacyLocalAppDataMigration",
    "LocalAppDataMigrationConflict",
    "LocalAppDataMigrationError",
    "LocalAppDataMigrationIntegrityError",
    "LocalAppDataMigrationReport",
    "MIGRATION_LOCK_NAME",
    "MIGRATION_MARKER_NAME",
]
