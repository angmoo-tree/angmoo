"""Pure deterministic export contracts for World Package v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
import unicodedata
from typing import Literal

from app.domains.world_packages.domain.content import ManagedImageAsset
from app.domains.world_packages.domain.canonical import canonical_sha256
from app.domains.world_packages.domain.manifest import (
    WorldPackageLicense,
    WorldPackageManifest,
)


WORLD_PACKAGE_PRODUCER_NAME = "Angmoo"
WORLD_PACKAGE_PRODUCER_VERSION = "0.4.0-1"
WORLD_PACKAGE_MIN_READER_VERSION = "0.4.0-1"
EXPORT_TOKEN_TTL_SECONDS = 5 * 60

WorldPackageAssetSlot = Literal[
    "world_banner",
    "character_avatar",
    "character_banner",
]
WorldPackageDeliveryMode = Literal["browser_download", "tauri_save_as"]


@dataclass(frozen=True, slots=True)
class WorldPackageMediaCandidate:
    candidate_key: str
    slot: WorldPackageAssetSlot
    source_url: str | None
    source_entity_id: str
    alt_text: str = ""


@dataclass(frozen=True, slots=True)
class WorldPackageResolvedAsset:
    candidate_key: str
    asset: ManagedImageAsset
    content: bytes


@dataclass(frozen=True, slots=True)
class WorldPackageResolvedAssets:
    assets: tuple[WorldPackageResolvedAsset, ...]
    excluded_external_candidate_keys: tuple[str, ...] = ()

    def reference_for(self, candidate_key: str) -> str | None:
        for item in self.assets:
            if item.candidate_key == candidate_key:
                return item.asset.ref
        return None


@dataclass(frozen=True, slots=True)
class WorldPackageSourceIdentity:
    package_id: str
    next_version: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WorldPackageVersionPreview:
    package_version: int
    replayed_seed: bool


@dataclass(frozen=True, slots=True)
class WorldPackageExportRegistryRecord:
    export_id: str
    package_id: str
    package_version: int
    source_world_id: str
    seed_digest: str
    manifest_digest: str
    license_expression: str
    delivery_mode: WorldPackageDeliveryMode
    delivered_at: datetime


@dataclass(frozen=True, slots=True)
class WorldPackageExportPreview:
    source_world_id: str
    source_fingerprint: str
    package_id: str
    package_version: int
    seed_digest: str
    recommended_filename: str
    included_autonomous_characters: int
    excluded_owner_controlled_characters: int
    included_assets: int
    excluded_external_assets: int
    warnings: tuple[str, ...]
    license: WorldPackageLicense


@dataclass(frozen=True, slots=True)
class WorldPackageBuiltArchive:
    content: bytes
    manifest: WorldPackageManifest
    seed_digest: str
    manifest_digest: str
    archive_digest: str


@dataclass(frozen=True, slots=True)
class WorldPackagePreparedExport:
    operation_id: str
    download_token: str
    expires_at: datetime
    preview: WorldPackageExportPreview
    manifest_digest: str
    archive_digest: str
    archive_bytes: int


_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_SEPARATORS = re.compile(r"[\s._-]+")


def recommended_world_package_filename(world_name: str, package_version: int) -> str:
    """Return a safe filename hint without creating or remembering a directory."""

    normalized = unicodedata.normalize("NFC", world_name).strip()
    normalized = _UNSAFE_FILENAME.sub("-", normalized)
    normalized = _SEPARATORS.sub("-", normalized).strip(" .-")
    if not normalized or normalized.casefold() in _WINDOWS_RESERVED:
        normalized = "angmoo-world"
    normalized = normalized[:96].rstrip(" .-") or "angmoo-world"
    return f"{normalized}-v{package_version}.angmoo-world"


def world_package_seed_digest(
    *,
    world: object,
    characters: object,
    world_characters: object,
    asset_index: object,
    license: WorldPackageLicense,
    license_text: str | None,
) -> str:
    """Hash every input that can change deterministic package bytes."""

    return canonical_sha256(
        {
            "world": world,
            "characters": characters,
            "world_characters": world_characters,
            "asset_index": asset_index,
            "license": license,
            "license_text": license_text,
            "producer": {
                "name": WORLD_PACKAGE_PRODUCER_NAME,
                "version": WORLD_PACKAGE_PRODUCER_VERSION,
                "min_reader_version": WORLD_PACKAGE_MIN_READER_VERSION,
            },
        }
    )


__all__ = [
    "EXPORT_TOKEN_TTL_SECONDS",
    "WORLD_PACKAGE_MIN_READER_VERSION",
    "WORLD_PACKAGE_PRODUCER_NAME",
    "WORLD_PACKAGE_PRODUCER_VERSION",
    "WorldPackageBuiltArchive",
    "WorldPackageDeliveryMode",
    "WorldPackageExportPreview",
    "WorldPackageExportRegistryRecord",
    "WorldPackageMediaCandidate",
    "WorldPackagePreparedExport",
    "WorldPackageResolvedAsset",
    "WorldPackageResolvedAssets",
    "WorldPackageSourceIdentity",
    "WorldPackageVersionPreview",
    "recommended_world_package_filename",
    "world_package_seed_digest",
]
