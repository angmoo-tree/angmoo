"""Privacy-safe app/data compatibility checks for Windows installer updates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from app.integrations.ladybug_projection import (
    inspect_ladybug_projection_schema_version,
)
from app.runtime.persistence.sqlite_schema import SCHEMA_VERSION_TABLE


class InstallerUpdateContractError(RuntimeError):
    """Stable, user-content-free installer update failure."""


@dataclass(frozen=True)
class DataVersionRange:
    minimum_readable_version: int
    maximum_readable_version: int
    target_version: int

    @classmethod
    def from_payload(cls, payload: Any, *, kind: str) -> "DataVersionRange":
        if not isinstance(payload, dict):
            raise InstallerUpdateContractError(
                "installer_payload_manifest_invalid"
            )
        try:
            minimum = int(payload["minimum_readable_version"])
            maximum = int(payload["maximum_readable_version"])
            target = int(payload["target_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InstallerUpdateContractError(
                "installer_payload_manifest_invalid"
            ) from exc
        minimum_floor = 1 if kind == "sqlite" else 0
        if (
            minimum < minimum_floor
            or minimum > maximum
            or target < minimum
            or target > maximum
        ):
            raise InstallerUpdateContractError(
                "installer_payload_manifest_invalid"
            )
        return cls(minimum, maximum, target)


@dataclass(frozen=True)
class InstallerPayloadContract:
    product_version: str
    build_commit: str
    payload_generation: str
    sqlite: DataVersionRange
    ladybug: DataVersionRange

    @classmethod
    def load(cls, path: Path) -> "InstallerPayloadContract":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InstallerUpdateContractError(
                "installer_payload_manifest_invalid"
            ) from exc
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != 2:
            raise InstallerUpdateContractError(
                "installer_payload_manifest_invalid"
            )
        product_version = str(payload.get("product_version", ""))
        build_commit = str(payload.get("build_commit", ""))
        payload_generation = str(payload.get("payload_generation", ""))
        embedded_data = payload.get("embedded_data")
        files = payload.get("files")
        if (
            not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,63}", product_version)
            or not re.fullmatch(r"[0-9a-f]{40}", build_commit)
            or not re.fullmatch(r"[0-9a-f]{64}", payload_generation)
            or not isinstance(embedded_data, dict)
            or not isinstance(files, dict)
        ):
            raise InstallerUpdateContractError(
                "installer_payload_manifest_invalid"
            )
        sqlite = DataVersionRange.from_payload(
            embedded_data.get("sqlite"), kind="sqlite"
        )
        ladybug = DataVersionRange.from_payload(
            embedded_data.get("ladybug"), kind="ladybug"
        )
        host_sha256 = str(files.get("angmoo-desktop.exe", ""))
        sidecar_sha256 = str(files.get("angmoo-sidecar.exe", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", host_sha256) or not re.fullmatch(
            r"[0-9a-f]{64}", sidecar_sha256
        ):
            raise InstallerUpdateContractError(
                "installer_payload_manifest_invalid"
            )
        identity_source = "\n".join(
            (
                product_version,
                build_commit,
                host_sha256,
                sidecar_sha256,
                "sqlite:"
                f"{sqlite.minimum_readable_version}-"
                f"{sqlite.maximum_readable_version}->"
                f"{sqlite.target_version}",
                "ladybug:"
                f"{ladybug.minimum_readable_version}-"
                f"{ladybug.maximum_readable_version}->"
                f"{ladybug.target_version}",
            )
        )
        if hashlib.sha256(identity_source.encode("utf-8")).hexdigest() != payload_generation:
            raise InstallerUpdateContractError(
                "installer_payload_manifest_invalid"
            )
        return cls(
            product_version=product_version,
            build_commit=build_commit,
            payload_generation=payload_generation,
            sqlite=sqlite,
            ladybug=ladybug,
        )


@dataclass(frozen=True)
class InstallerCompatibilityResult:
    sqlite_source_version: int | None
    sqlite_target_version: int
    ladybug_source_version: int | None
    ladybug_target_version: int
    build_commit: str
    payload_generation: str

    def public_payload(self) -> dict[str, str | int | None]:
        return {
            "status": "compatible",
            "build_commit": self.build_commit,
            "payload_generation": self.payload_generation,
            "sqlite_source_version": self.sqlite_source_version,
            "sqlite_target_version": self.sqlite_target_version,
            "ladybug_source_version": self.ladybug_source_version,
            "ladybug_target_version": self.ladybug_target_version,
        }


def preflight_installer_embedded_data(
    *,
    data_root: Path,
    payload_manifest: Path,
) -> InstallerCompatibilityResult:
    contract = InstallerPayloadContract.load(payload_manifest.resolve())
    data_root = data_root.resolve()
    sqlite_version = _sqlite_data_version(data_root)
    ladybug_version = _ladybug_data_version(data_root)
    _require_compatible(
        sqlite_version,
        contract.sqlite,
        error_code="installer_sqlite_data_incompatible",
    )
    _require_compatible(
        ladybug_version,
        contract.ladybug,
        error_code="installer_ladybug_data_incompatible",
    )
    return InstallerCompatibilityResult(
        sqlite_source_version=sqlite_version,
        sqlite_target_version=contract.sqlite.target_version,
        ladybug_source_version=ladybug_version,
        ladybug_target_version=contract.ladybug.target_version,
        build_commit=contract.build_commit,
        payload_generation=contract.payload_generation,
    )


def _require_compatible(
    current: int | None,
    allowed: DataVersionRange,
    *,
    error_code: str,
) -> None:
    if current is None:
        return
    if not (
        allowed.minimum_readable_version
        <= current
        <= allowed.maximum_readable_version
    ):
        raise InstallerUpdateContractError(error_code)


def _sqlite_data_version(data_root: Path) -> int | None:
    canonical = data_root / "canonical"
    marker = _generation_marker(canonical)
    if marker is not None:
        return marker
    fallback = canonical / "generations" / "er6-preview-v1" / "angmoo.sqlite3"
    if not fallback.is_file():
        return None
    try:
        connection = sqlite3.connect(
            f"file:{fallback.resolve().as_posix()}?mode=ro",
            uri=True,
        )
        try:
            row = connection.execute(
                f"SELECT schema_version FROM {SCHEMA_VERSION_TABLE} "
                "WHERE singleton_key = 1"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise InstallerUpdateContractError(
            "installer_sqlite_data_incompatible"
        ) from exc
    if row is None:
        raise InstallerUpdateContractError(
            "installer_sqlite_data_incompatible"
        )
    return int(row[0])


def _ladybug_data_version(data_root: Path) -> int | None:
    graph = data_root / "graph"
    marker = _generation_marker(graph)
    if marker is not None:
        return marker
    legacy_root = graph / "ladybug"
    try:
        return inspect_ladybug_projection_schema_version(legacy_root)
    except Exception as exc:  # noqa: BLE001 - stable installer boundary
        raise InstallerUpdateContractError(
            "installer_ladybug_data_incompatible"
        ) from exc


def _generation_marker(root: Path) -> int | None:
    path = root / "current-generation.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != 1:
            raise ValueError
        data_version = int(payload["data_version"])
        if data_version < 0:
            raise ValueError
        return data_version
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise InstallerUpdateContractError(
            "installer_generation_marker_invalid"
        ) from exc


__all__ = [
    "DataVersionRange",
    "InstallerCompatibilityResult",
    "InstallerPayloadContract",
    "InstallerUpdateContractError",
    "preflight_installer_embedded_data",
]
