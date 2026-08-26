"""Deterministic World Package export orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.world_packages.domain.content import (
    AssetIndexDocument,
    CharactersDocument,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.export import (
    WorldPackageBuiltArchive,
    WorldPackageExportPreview,
    WorldPackageResolvedAssets,
    WorldPackageSourceIdentity,
    recommended_world_package_filename,
    world_package_seed_digest,
)
from app.domains.world_packages.domain.manifest import WorldPackageLicense
from app.domains.world_packages.domain.license_policy import (
    SUPPORTED_LICENSE_EXPRESSIONS,
    validate_world_package_license,
)
from app.domains.world_packages.domain.package_policy import WorldPackagePolicy
from app.domains.world_packages.domain.seed import WorldPackageSourceSnapshot
from app.domains.world_packages.ports.managed_assets import ManagedPackageAssetPort
from app.domains.world_packages.ports.package_archive import WorldPackageArchivePort
from app.domains.world_packages.ports.registry import WorldPackageRegistryPort
from app.domains.world_packages.ports.source_snapshot import (
    WorldPackageSourceSnapshotPort,
)


@dataclass(frozen=True, slots=True)
class WorldPackageExportMaterial:
    snapshot: WorldPackageSourceSnapshot
    identity: WorldPackageSourceIdentity
    world: PortableWorldDefinition
    characters: CharactersDocument
    world_characters: WorldCharactersDocument
    asset_index: AssetIndexDocument
    assets: WorldPackageResolvedAssets
    license: WorldPackageLicense
    license_text: str | None
    seed_digest: str
    package_version: int


class ExportWorldPackage:
    def __init__(
        self,
        *,
        source: WorldPackageSourceSnapshotPort,
        assets: ManagedPackageAssetPort,
        registry: WorldPackageRegistryPort,
        archive: WorldPackageArchivePort,
    ) -> None:
        self._source = source
        self._assets = assets
        self._registry = registry
        self._archive = archive

    def preview(
        self,
        *,
        source_world_id: str,
        local_owner_id: str,
        license: WorldPackageLicense,
        license_text: str | None,
    ) -> WorldPackageExportPreview:
        material = self._materialize(
            source_world_id=source_world_id,
            local_owner_id=local_owner_id,
            license=license,
            license_text=license_text,
        )
        return self._preview(material)

    def build(
        self,
        *,
        source_world_id: str,
        local_owner_id: str,
        license: WorldPackageLicense,
        license_text: str | None,
    ) -> tuple[WorldPackageExportPreview, WorldPackageBuiltArchive]:
        material = self._materialize(
            source_world_id=source_world_id,
            local_owner_id=local_owner_id,
            license=license,
            license_text=license_text,
        )
        archive = self._archive.build(
            identity=material.identity,
            package_version=material.package_version,
            world=material.world,
            characters=material.characters,
            world_characters=material.world_characters,
            asset_index=material.asset_index,
            resolved_assets=material.assets,
            license=material.license,
            license_text=material.license_text,
        )
        if archive.seed_digest != material.seed_digest:
            raise WorldPackageContractError(
                WorldPackageReasonCode.INTEGRITY_MISMATCH
            )
        return self._preview(material), archive

    def _materialize(
        self,
        *,
        source_world_id: str,
        local_owner_id: str,
        license: WorldPackageLicense,
        license_text: str | None,
    ) -> WorldPackageExportMaterial:
        normalized_license_text = _validate_license(license, license_text)
        identity = self._registry.resolve_export_source(
            source_world_id=source_world_id
        )
        snapshot = self._source.snapshot(
            source_world_id=source_world_id,
            local_owner_id=local_owner_id,
        )
        resolved = self._assets.resolve_export_assets(
            candidates=snapshot.media_candidates
        )
        world = snapshot.world.model_copy(
            update={
                "banner_asset_ref": resolved.reference_for("world:banner"),
            }
        )
        characters = CharactersDocument(
            schema_version="characters-content-v1",
            characters=[
                item.model_copy(
                    update={
                        "avatar_asset_ref": resolved.reference_for(
                            f"{item.ref}:avatar"
                        ),
                        "banner_asset_ref": resolved.reference_for(
                            f"{item.ref}:banner"
                        ),
                    }
                )
                for item in snapshot.characters
            ],
        )
        world_characters = WorldCharactersDocument(
            schema_version="world-characters-content-v1",
            world_ref="world",
            characters=list(snapshot.world_characters),
        )
        unique_assets = {
            item.asset.ref: item.asset for item in resolved.assets
        }
        asset_index = AssetIndexDocument(
            schema_version="assets-index-v1",
            assets=[unique_assets[key] for key in sorted(unique_assets)],
        )
        if len(asset_index.assets) > WorldPackagePolicy.MAX_ASSETS:
            raise WorldPackageContractError(
                WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED
            )
        seed_digest = world_package_seed_digest(
            world=world,
            characters=characters,
            world_characters=world_characters,
            asset_index=asset_index,
            license=license,
            license_text=normalized_license_text,
        )
        version = self._registry.preview_export_version(
            package_id=identity.package_id,
            seed_digest=seed_digest,
        )
        current = self._source.snapshot(
            source_world_id=source_world_id,
            local_owner_id=local_owner_id,
        )
        if current.source_fingerprint != snapshot.source_fingerprint:
            raise WorldPackageContractError(WorldPackageReasonCode.SOURCE_CHANGED)
        return WorldPackageExportMaterial(
            snapshot=snapshot,
            identity=identity,
            world=world,
            characters=characters,
            world_characters=world_characters,
            asset_index=asset_index,
            assets=resolved,
            license=license,
            license_text=normalized_license_text,
            seed_digest=seed_digest,
            package_version=version.package_version,
        )

    @staticmethod
    def _preview(material: WorldPackageExportMaterial) -> WorldPackageExportPreview:
        external_count = len(material.assets.excluded_external_candidate_keys)
        warnings = (
            ("external_asset_excluded",) if external_count else ()
        )
        return WorldPackageExportPreview(
            source_world_id=material.snapshot.source_world_id,
            source_fingerprint=material.snapshot.source_fingerprint,
            package_id=material.identity.package_id,
            package_version=material.package_version,
            seed_digest=material.seed_digest,
            recommended_filename=recommended_world_package_filename(
                material.snapshot.world.name,
                material.package_version,
            ),
            included_autonomous_characters=len(material.characters.characters),
            excluded_owner_controlled_characters=(
                material.snapshot.excluded_owner_controlled_characters
            ),
            included_assets=len(material.asset_index.assets),
            excluded_external_assets=external_count,
            warnings=warnings,
            license=material.license,
        )


def _validate_license(
    license: WorldPackageLicense, license_text: str | None
) -> str | None:
    validate_world_package_license(license, license_text)
    return license_text


__all__ = [
    "ExportWorldPackage",
    "SUPPORTED_LICENSE_EXPRESSIONS",
    "WorldPackageExportMaterial",
]
