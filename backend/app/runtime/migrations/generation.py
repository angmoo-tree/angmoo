"""Atomic embedded-data generation selection and cross-process locking."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import Any


class EmbeddedGenerationError(RuntimeError):
    """Privacy-safe embedded generation lifecycle failure."""


class EmbeddedUpgradeLock:
    """Own one non-blocking byte lock before any embedded store is opened."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: Any | None = None

    def __enter__(self) -> "EmbeddedUpgradeLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise EmbeddedGenerationError("embedded_upgrade_locked") from None
        self._handle = handle
        return self

    def __exit__(self, *_: object) -> None:
        handle = self._handle
        if handle is None:
            return
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        self._handle = None


class EmbeddedGenerationController:
    """Select and promote one owned canonical or graph generation."""

    def __init__(
        self,
        root: Path,
        *,
        artifact_relative_path: str,
    ) -> None:
        self.root = root.resolve()
        self.generations = self.root / "generations"
        self.current_marker = self.root / "current-generation.json"
        self.previous_marker = self.root / "previous-generation.json"
        self.artifact_relative_path = artifact_relative_path

    def selected_relative_path(self, fallback: str) -> str:
        payload = self.current()
        if payload is None:
            return _validate_relative_path(fallback)
        return _validate_relative_path(str(payload.get("relative_path") or ""))

    def selected_root(self, fallback: str) -> Path:
        relative = self.selected_relative_path(fallback)
        root = _owned_relative(self.root, relative)
        if not (root / self.artifact_relative_path).exists():
            raise EmbeddedGenerationError("generation_artifact_missing")
        return root

    def current(self) -> dict[str, Any] | None:
        if not self.current_marker.is_file():
            return None
        payload = _read_json(self.current_marker)
        if int(payload.get("schema_version", 0)) != 1:
            raise EmbeddedGenerationError("generation_marker_invalid")
        if not payload.get("relative_path") and payload.get("generation"):
            payload["relative_path"] = (
                Path("generations") / str(payload["generation"])
            ).as_posix()
        if not payload.get("manifest_sha256") and payload.get("content_sha256"):
            payload["manifest_sha256"] = payload["content_sha256"]
        _validate_relative_path(str(payload.get("relative_path") or ""))
        _require_sha256(str(payload.get("manifest_sha256") or ""))
        return payload

    def promote(
        self,
        relative_path: str,
        *,
        manifest_sha256: str,
        data_version: int,
        previous_relative_path: str | None = None,
        previous_manifest_sha256: str | None = None,
        previous_data_version: int | None = None,
    ) -> dict[str, Any]:
        relative = _validate_relative_path(relative_path)
        target = _owned_relative(self.root, relative)
        if not (target / self.artifact_relative_path).exists():
            raise EmbeddedGenerationError("generation_artifact_missing")
        self.root.mkdir(parents=True, exist_ok=True)
        if self.current_marker.is_file():
            shutil.copy2(self.current_marker, self.previous_marker)
        elif previous_relative_path is not None:
            if previous_manifest_sha256 is None or previous_data_version is None:
                raise EmbeddedGenerationError("previous_generation_invalid")
            previous_payload = self._marker_payload(
                previous_relative_path,
                manifest_sha256=previous_manifest_sha256,
                data_version=previous_data_version,
            )
            _write_json_atomic(self.previous_marker, previous_payload)
        payload = self._marker_payload(
            relative,
            manifest_sha256=manifest_sha256,
            data_version=data_version,
        )
        _write_json_atomic(self.current_marker, payload)
        return payload

    def _marker_payload(
        self,
        relative_path: str,
        *,
        manifest_sha256: str,
        data_version: int,
    ) -> dict[str, Any]:
        relative = _validate_relative_path(relative_path)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "relative_path": relative,
            "manifest_sha256": _require_sha256(manifest_sha256),
            "data_version": int(data_version),
        }
        if self.artifact_relative_path == "angmoo.sqlite3":
            payload["generation"] = Path(relative).name
            payload["content_sha256"] = payload["manifest_sha256"]
        return payload

    def finalize_staging(self, staging: Path, final_relative_path: str) -> Path:
        relative = _validate_relative_path(final_relative_path)
        final = _owned_relative(self.root, relative)
        staging = staging.resolve()
        if staging.parent != self.generations.resolve():
            raise EmbeddedGenerationError("staging_path_not_owned")
        if final.exists():
            raise EmbeddedGenerationError("generation_target_exists")
        final.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(final)
        return final


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    _write_json_atomic(path, payload)


def read_json_object(path: Path) -> dict[str, Any]:
    return _read_json(path)


def _owned_relative(root: Path, relative: str) -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate == root or root not in candidate.parents:
        raise EmbeddedGenerationError("generation_path_not_owned")
    return candidate


def _validate_relative_path(value: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise EmbeddedGenerationError("generation_path_invalid")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/\\"
    if any(character not in allowed for character in value):
        raise EmbeddedGenerationError("generation_path_invalid")
    return path.as_posix()


def _require_sha256(value: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise EmbeddedGenerationError("generation_digest_invalid")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EmbeddedGenerationError("generation_marker_invalid") from exc
    if not isinstance(payload, dict):
        raise EmbeddedGenerationError("generation_marker_invalid")
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


__all__ = [
    "EmbeddedGenerationController",
    "EmbeddedGenerationError",
    "EmbeddedUpgradeLock",
    "read_json_object",
    "write_json_atomic",
]
