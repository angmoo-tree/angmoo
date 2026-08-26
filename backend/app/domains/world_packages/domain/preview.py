"""Pure records for bounded World Package staging and preview."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domains.world_packages.domain.collision_policy import (
    WorldPackageCollisionPlan,
)
from app.domains.world_packages.domain.content import (
    AssetIndexDocument,
    CharactersDocument,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.domain.import_state import (
    WorldPackageImportState,
    WorldPackageTrustState,
)
from app.domains.world_packages.domain.license_policy import (
    WorldPackageLicenseAssessment,
)
from app.domains.world_packages.domain.manifest import (
    WorldPackageLicense,
    WorldPackageManifest,
)


IMPORT_PREVIEW_SCHEMA_VERSION = "world-package-import-preview-v1"
IMPORT_PREVIEW_TOKEN_TTL_SECONDS = 30 * 60


@dataclass(frozen=True, slots=True)
class WorldPackageNormalizedAsset:
    source_ref: str
    normalized_ref: str
    normalized_sha256: str
    normalized_bytes: int
    width: int
    height: int
    alt_text: str


@dataclass(frozen=True, slots=True, repr=False)
class WorldPackageNormalizedAssetPayload:
    """Commit-only normalized bytes; never serialized into preview or logs."""

    source_ref: str
    normalized_ref: str
    normalized_sha256: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ValidatedWorldPackage:
    operation_id: str
    archive_digest: str
    manifest_digest: str
    manifest: WorldPackageManifest
    world: PortableWorldDefinition
    characters: CharactersDocument
    world_characters: WorldCharactersDocument
    asset_index: AssetIndexDocument
    normalized_assets: tuple[WorldPackageNormalizedAsset, ...]
    normalized_asset_payloads: tuple[WorldPackageNormalizedAssetPayload, ...]
    license_text: str | None
    license_assessment: WorldPackageLicenseAssessment


@dataclass(frozen=True, slots=True)
class WorldPackagePreviewAssessment:
    trust_state: WorldPackageTrustState
    collision_plan: WorldPackageCollisionPlan
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorldPackageImportPreview:
    schema_version: str
    state: WorldPackageImportState
    operation_id: str
    archive_digest: str
    content_digest: str
    package_id: str
    package_version: int
    producer_name: str
    producer_version: str
    min_reader_version: str
    world_contract_version: str
    trust_state: WorldPackageTrustState
    license: WorldPackageLicense
    world_name: str
    world_tagline: str
    character_names: tuple[str, ...]
    role_count: int
    place_count: int
    rule_count: int
    glossary_count: int
    asset_count: int
    asset_bytes: int
    total_decoded_pixels: int
    excluded_owner_controlled_characters: int
    excluded_runtime_records: int
    collision_plan: WorldPackageCollisionPlan
    normalized_assets: tuple[WorldPackageNormalizedAsset, ...]
    warnings: tuple[str, ...]
    blocking_issues: tuple[str, ...]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class WorldPackagePreparedPreview:
    preview: WorldPackageImportPreview
    preview_token: str


__all__ = [
    "IMPORT_PREVIEW_SCHEMA_VERSION",
    "IMPORT_PREVIEW_TOKEN_TTL_SECONDS",
    "ValidatedWorldPackage",
    "WorldPackageImportPreview",
    "WorldPackageNormalizedAsset",
    "WorldPackageNormalizedAssetPayload",
    "WorldPackagePreparedPreview",
    "WorldPackagePreviewAssessment",
]
