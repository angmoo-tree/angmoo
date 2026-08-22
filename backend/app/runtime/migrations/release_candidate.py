"""Recoverable ER6 synthetic backup, restore, and generation-switch proof.

The adapter is deliberately synthetic-fixture-only. It can carry an APP_SECRET
and encrypted credential envelope for migration validation, but refuses a
fixture marked as containing a real credential. Backup directories are never
uploaded by the ER6 workflow.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from app.domains.runtime.ports.release_candidate import (
    ReleaseCandidateBackupFile,
    ReleaseCandidateBackupManifest,
    ReleaseCandidateBackupReport,
)
from app.domains.runtime.ports.runtime_data_path import RuntimeDataPathPort

BACKUP_MANIFEST_NAME = "release-candidate-backup.json"
SYNTHETIC_FIXTURE_MARKER = "synthetic-fixture.json"
GENERATION_MARKER_NAME = "current-generation.json"
PREVIOUS_GENERATION_MARKER_NAME = "previous-generation.json"
_OWNED_DATA_DIRECTORIES = ("canonical", "graph", "search", "media", "secrets")


class ReleaseCandidateBackupError(RuntimeError):
    pass


class ReleaseCandidateIntegrityError(ReleaseCandidateBackupError):
    pass


class ReleaseCandidateSyntheticOnlyError(ReleaseCandidateBackupError):
    pass


class ReleaseCandidateRestoreTargetError(ReleaseCandidateBackupError):
    pass


class SyntheticReleaseCandidateBackup:
    def __init__(
        self,
        *,
        data_paths: RuntimeDataPathPort,
        app_version: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._data_paths = data_paths
        self._app_version = app_version
        self._now = now or (lambda: datetime.now(UTC))

    def create(self, backup_root: str | Path) -> ReleaseCandidateBackupReport:
        source_root = self._data_paths.resolve().root.resolve()
        marker = _read_synthetic_marker(source_root / SYNTHETIC_FIXTURE_MARKER)
        target = Path(backup_root).resolve()
        if target == source_root or source_root in target.parents:
            raise ReleaseCandidateBackupError("backup_target_is_inside_source")
        if target.exists():
            raise ReleaseCandidateBackupError("backup_target_already_exists")
        temporary = target.with_name(f".{target.name}.tmp-{uuid4().hex}")
        temporary.mkdir(parents=True)
        try:
            shutil.copy2(source_root / SYNTHETIC_FIXTURE_MARKER, temporary)
            for directory in _OWNED_DATA_DIRECTORIES:
                source = source_root / directory
                if source.exists():
                    _copy_tree_without_links(source, temporary / directory)
            files = _summarize_files(temporary)
            manifest = _manifest(
                app_version=self._app_version,
                fixture_id=marker["fixture_id"],
                created_at=self._now().astimezone(UTC).isoformat(),
                files=files,
            )
            _write_json_atomic(temporary / BACKUP_MANIFEST_NAME, asdict(manifest))
            temporary.replace(target)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return self.inspect(target)

    def inspect(self, backup_root: str | Path) -> ReleaseCandidateBackupReport:
        root = Path(backup_root).resolve()
        manifest = _read_manifest(root / BACKUP_MANIFEST_NAME)
        _read_synthetic_marker(root / SYNTHETIC_FIXTURE_MARKER)
        actual = _summarize_files(root)
        expected = manifest.files
        if actual != expected:
            raise ReleaseCandidateIntegrityError("backup_file_digest_mismatch")
        if _content_sha256(actual) != manifest.content_sha256:
            raise ReleaseCandidateIntegrityError("backup_content_digest_mismatch")
        return ReleaseCandidateBackupReport(
            manifest=manifest,
            backup_root=str(root),
        )

    def restore(
        self,
        backup_root: str | Path,
        target_root: str | Path,
    ) -> ReleaseCandidateBackupReport:
        report = self.inspect(backup_root)
        source = Path(backup_root).resolve()
        target = Path(target_root).resolve()
        if target == source or source in target.parents:
            raise ReleaseCandidateRestoreTargetError("restore_target_is_inside_backup")
        if target.exists() and any(target.iterdir()):
            raise ReleaseCandidateRestoreTargetError("restore_target_not_empty")
        temporary = target.with_name(f".{target.name}.restore-{uuid4().hex}")
        temporary.mkdir(parents=True)
        try:
            shutil.copy2(source / SYNTHETIC_FIXTURE_MARKER, temporary)
            for directory in _OWNED_DATA_DIRECTORIES:
                source_directory = source / directory
                if source_directory.exists():
                    _copy_tree_without_links(
                        source_directory,
                        temporary / directory,
                    )
            restored_files = _summarize_files(temporary)
            if restored_files != report.manifest.files:
                raise ReleaseCandidateIntegrityError("restored_file_digest_mismatch")
            _write_json_atomic(
                temporary / BACKUP_MANIFEST_NAME,
                asdict(report.manifest),
            )
            if target.exists():
                target.rmdir()
            temporary.replace(target)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return self.inspect(target)


class RuntimeGenerationController:
    """Persist an atomic, rollback-capable generation selection marker."""

    def __init__(self, data_paths: RuntimeDataPathPort) -> None:
        self._canonical = data_paths.resolve().canonical.resolve()
        self._generations = self._canonical / "generations"
        self._current = self._canonical / GENERATION_MARKER_NAME
        self._previous = self._canonical / PREVIOUS_GENERATION_MARKER_NAME

    def promote(
        self,
        generation: str,
        *,
        content_sha256: str,
    ) -> dict[str, str | int]:
        generation_root = _owned_generation(self._generations, generation)
        if not (generation_root / "angmoo.sqlite3").is_file():
            raise ReleaseCandidateBackupError("generation_database_missing")
        self._canonical.mkdir(parents=True, exist_ok=True)
        if self._current.is_file():
            shutil.copy2(self._current, self._previous)
        payload = {
            "schema_version": 1,
            "generation": generation,
            "content_sha256": _require_sha256(content_sha256),
        }
        _write_json_atomic(self._current, payload)
        return payload

    def rollback(self) -> dict[str, Any]:
        if not self._previous.is_file():
            raise ReleaseCandidateBackupError("previous_generation_missing")
        payload = _read_json_object(self._previous)
        generation = str(payload.get("generation", ""))
        generation_root = _owned_generation(self._generations, generation)
        if not (generation_root / "angmoo.sqlite3").is_file():
            raise ReleaseCandidateBackupError("generation_database_missing")
        _require_sha256(str(payload.get("content_sha256", "")))
        _write_json_atomic(self._current, payload)
        return payload

    def current(self) -> dict[str, Any] | None:
        if not self._current.is_file():
            return None
        payload = _read_json_object(self._current)
        return payload


def _read_synthetic_marker(path: Path) -> dict[str, Any]:
    payload = _read_json_object(path)
    if payload.get("schema_version") != 1:
        raise ReleaseCandidateSyntheticOnlyError("synthetic_marker_version_invalid")
    if payload.get("synthetic_fixture") is not True:
        raise ReleaseCandidateSyntheticOnlyError("personal_data_backup_refused")
    if payload.get("contains_real_credentials") is not False:
        raise ReleaseCandidateSyntheticOnlyError("real_credential_backup_refused")
    fixture_id = payload.get("fixture_id")
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise ReleaseCandidateSyntheticOnlyError("synthetic_fixture_id_missing")
    return payload


def _read_manifest(path: Path) -> ReleaseCandidateBackupManifest:
    payload = _read_json_object(path)
    try:
        files = tuple(
            ReleaseCandidateBackupFile(**item) for item in payload.pop("files")
        )
        manifest = ReleaseCandidateBackupManifest(files=files, **payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ReleaseCandidateIntegrityError("backup_manifest_invalid") from exc
    if manifest.schema_version != 1:
        raise ReleaseCandidateIntegrityError("backup_manifest_version_invalid")
    if not manifest.synthetic_fixture or manifest.contains_real_credentials:
        raise ReleaseCandidateIntegrityError("backup_manifest_policy_invalid")
    return manifest


def _manifest(
    *,
    app_version: str,
    fixture_id: str,
    created_at: str,
    files: tuple[ReleaseCandidateBackupFile, ...],
) -> ReleaseCandidateBackupManifest:
    return ReleaseCandidateBackupManifest(
        schema_version=1,
        app_version=app_version,
        fixture_id=fixture_id,
        created_at=created_at,
        synthetic_fixture=True,
        contains_real_credentials=False,
        files=files,
        content_sha256=_content_sha256(files),
    )


def _copy_tree_without_links(source: Path, target: Path) -> None:
    for candidate in sorted(source.rglob("*")):
        if candidate.is_symlink():
            raise ReleaseCandidateBackupError("backup_symbolic_link_refused")
        relative = candidate.relative_to(source)
        destination = target / relative
        if candidate.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif candidate.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, destination)


def _summarize_files(root: Path) -> tuple[ReleaseCandidateBackupFile, ...]:
    files: list[ReleaseCandidateBackupFile] = []
    for candidate in sorted(root.rglob("*")):
        if candidate.name == BACKUP_MANIFEST_NAME:
            continue
        if candidate.is_symlink():
            raise ReleaseCandidateIntegrityError("backup_symbolic_link_refused")
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root).as_posix()
        _safe_relative_path(relative)
        files.append(
            ReleaseCandidateBackupFile(
                relative_path=relative,
                size_bytes=candidate.stat().st_size,
                sha256=_sha256_file(candidate),
            )
        )
    return tuple(files)


def _content_sha256(files: tuple[ReleaseCandidateBackupFile, ...]) -> str:
    payload = [asdict(item) for item in files]
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ReleaseCandidateIntegrityError("backup_path_invalid")
    if relative.parts[0] not in {*_OWNED_DATA_DIRECTORIES, SYNTHETIC_FIXTURE_MARKER}:
        raise ReleaseCandidateIntegrityError("backup_path_not_owned")
    return relative


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseCandidateIntegrityError("backup_json_invalid") from exc
    if not isinstance(payload, dict):
        raise ReleaseCandidateIntegrityError("backup_json_not_object")
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _owned_generation(root: Path, generation: str) -> Path:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if not generation or any(character not in allowed for character in generation):
        raise ReleaseCandidateBackupError("generation_name_invalid")
    candidate = (root / generation).resolve()
    if candidate.parent != root.resolve():
        raise ReleaseCandidateBackupError("generation_path_not_owned")
    return candidate


def _require_sha256(value: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ReleaseCandidateBackupError("generation_digest_invalid")
    return value


__all__ = [
    "BACKUP_MANIFEST_NAME",
    "GENERATION_MARKER_NAME",
    "PREVIOUS_GENERATION_MARKER_NAME",
    "SYNTHETIC_FIXTURE_MARKER",
    "ReleaseCandidateBackupError",
    "ReleaseCandidateIntegrityError",
    "ReleaseCandidateRestoreTargetError",
    "ReleaseCandidateSyntheticOnlyError",
    "RuntimeGenerationController",
    "SyntheticReleaseCandidateBackup",
]
