"""Defence-in-depth scan for local-runtime data in a final World Package."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import PurePosixPath
import re
from typing import Iterable
from zipfile import BadZipFile, ZipFile


_REQUIRED_JSON_ENTRIES = {
    "manifest.json",
    "content/world.json",
    "content/characters.json",
    "content/world-characters.json",
    "assets/index.json",
}
_OPTIONAL_ENTRIES = {"LICENSE.txt"}
_ASSET_ENTRY = re.compile(r"assets/sha256-[0-9a-f]{64}\.webp\Z")
_FORBIDDEN_JSON_KEYS = {
    "api_key",
    "app_secret",
    "autonomous_enabled",
    "character_active_world",
    "character_id",
    "credential",
    "credential_id",
    "daily_activity_plan",
    "encrypted_api_key",
    "graph_projection_outbox",
    "installation_id",
    "memory",
    "owner_id",
    "owner_user_id",
    "post_id",
    "provider_secret",
    "relationship_state",
    "routine_post",
    "social_event",
    "source_world_id",
    "world_activity_candidate",
    "world_character_id",
    "world_id",
}


class WorldPackageExclusionError(ValueError):
    """Raised without echoing the private value that caused the failure."""


@dataclass(frozen=True, slots=True)
class WorldPackageExclusionReport:
    entry_count: int
    json_document_count: int
    scanned_uncompressed_bytes: int


def _normalized_key(value: object) -> str:
    return str(value).strip().casefold().replace("-", "_")


def _walk_json_keys(value: object) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield _normalized_key(key)
            yield from _walk_json_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json_keys(child)


def _validate_entry_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or name.startswith("//")
        or re.match(r"^[A-Za-z]:", name)
    ):
        raise WorldPackageExclusionError("world_package_invalid_entry_name")
    if (
        name not in _REQUIRED_JSON_ENTRIES
        and name not in _OPTIONAL_ENTRIES
        and _ASSET_ENTRY.fullmatch(name) is None
    ):
        raise WorldPackageExclusionError("world_package_unknown_entry")


def scan_world_package_bytes(
    content: bytes,
    *,
    forbidden_values: Iterable[bytes | str] = (),
) -> WorldPackageExclusionReport:
    """Scan one bounded v1 artifact without logging private marker values."""

    markers = tuple(
        marker.encode("utf-8") if isinstance(marker, str) else bytes(marker)
        for marker in forbidden_values
        if marker
    )
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = archive.namelist()
            if len(names) != len(set(name.casefold() for name in names)):
                raise WorldPackageExclusionError(
                    "world_package_duplicate_entry"
                )
            for name in names:
                _validate_entry_name(name)
            if not _REQUIRED_JSON_ENTRIES.issubset(names):
                raise WorldPackageExclusionError(
                    "world_package_required_entry_missing"
                )

            json_count = 0
            scanned_bytes = 0
            for name in names:
                payload = archive.read(name)
                scanned_bytes += len(payload)
                if any(marker in payload for marker in markers):
                    raise WorldPackageExclusionError(
                        "world_package_private_value_detected"
                    )
                if not name.endswith(".json"):
                    continue
                json_count += 1
                try:
                    document = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise WorldPackageExclusionError(
                        "world_package_json_invalid"
                    ) from exc
                forbidden_keys = _FORBIDDEN_JSON_KEYS.intersection(
                    _walk_json_keys(document)
                )
                if forbidden_keys:
                    raise WorldPackageExclusionError(
                        "world_package_forbidden_field_detected"
                    )
    except BadZipFile as exc:
        raise WorldPackageExclusionError("world_package_archive_invalid") from exc

    return WorldPackageExclusionReport(
        entry_count=len(names),
        json_document_count=json_count,
        scanned_uncompressed_bytes=scanned_bytes,
    )


__all__ = [
    "WorldPackageExclusionError",
    "WorldPackageExclusionReport",
    "scan_world_package_bytes",
]
