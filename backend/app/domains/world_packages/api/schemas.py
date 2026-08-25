"""HTTP schemas for deterministic World Package export and safe preview."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.world_packages.domain.export import WorldPackageExportPreview
from app.domains.world_packages.domain.manifest import WorldPackageLicense
from app.domains.world_packages.domain.preview import (
    WorldPackageImportPreview,
    WorldPackagePreparedPreview,
)


class WorldPackageExportSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorldPackageExportRequest(WorldPackageExportSchema):
    license_expression: str = Field(min_length=1, max_length=160)
    attribution: str = Field(default="", max_length=1000)
    source_url: str | None = Field(default=None, max_length=2048)
    license_text: str | None = Field(default=None, max_length=256 * 1024)
    confirm_export_rights: Literal[True]
    confirm_license: Literal[True]
    confirm_exclusions: Literal[True]

    def domain_license(self) -> WorldPackageLicense:
        is_reference = self.license_expression.startswith("LicenseRef-")
        return WorldPackageLicense(
            expression=self.license_expression,
            attribution=self.attribution,
            source_url=self.source_url,
            license_text_path="LICENSE.txt" if is_reference else None,
        )


class WorldPackageExportPreviewRead(WorldPackageExportSchema):
    source_world_id: str
    package_id: str
    package_version: int
    seed_digest: str
    recommended_filename: str
    included_autonomous_characters: int
    excluded_owner_controlled_characters: int
    included_assets: int
    excluded_external_assets: int
    warnings: list[str]
    license: WorldPackageLicense

    @classmethod
    def from_domain(
        cls, value: WorldPackageExportPreview
    ) -> "WorldPackageExportPreviewRead":
        return cls(
            source_world_id=value.source_world_id,
            package_id=value.package_id,
            package_version=value.package_version,
            seed_digest=value.seed_digest,
            recommended_filename=value.recommended_filename,
            included_autonomous_characters=(
                value.included_autonomous_characters
            ),
            excluded_owner_controlled_characters=(
                value.excluded_owner_controlled_characters
            ),
            included_assets=value.included_assets,
            excluded_external_assets=value.excluded_external_assets,
            warnings=list(value.warnings),
            license=value.license,
        )


class WorldPackagePreparedExportRead(WorldPackageExportSchema):
    operation_id: str
    download_token: str
    download_path: str
    expires_at: datetime
    preview: WorldPackageExportPreviewRead
    manifest_digest: str
    archive_digest: str
    archive_bytes: int
    replayed_request: bool


class WorldPackageCharacterCollisionRead(WorldPackageExportSchema):
    source_ref: str
    display_name: str
    planned_handle: str


class WorldPackageCollisionPlanRead(WorldPackageExportSchema):
    planned_world_slug: str
    characters: list[WorldPackageCharacterCollisionRead]
    duplicate_state: str
    commit_allowed_by_default: bool


class WorldPackageNormalizedAssetRead(WorldPackageExportSchema):
    source_ref: str
    normalized_ref: str
    normalized_sha256: str
    normalized_bytes: int
    width: int
    height: int
    alt_text: str


class WorldPackageImportPreviewRead(WorldPackageExportSchema):
    schema_version: str
    state: str
    operation_id: str
    archive_digest: str
    content_digest: str
    package_id: str
    package_version: int
    producer_name: str
    producer_version: str
    min_reader_version: str
    world_contract_version: str
    trust_state: str
    license: WorldPackageLicense
    world_name: str
    world_tagline: str
    character_names: list[str]
    role_count: int
    place_count: int
    rule_count: int
    glossary_count: int
    asset_count: int
    asset_bytes: int
    total_decoded_pixels: int
    excluded_owner_controlled_characters: int
    excluded_runtime_records: int
    collision_plan: WorldPackageCollisionPlanRead
    normalized_assets: list[WorldPackageNormalizedAssetRead]
    warnings: list[str]
    blocking_issues: list[str]
    expires_at: datetime

    @classmethod
    def from_domain(
        cls, value: WorldPackageImportPreview
    ) -> "WorldPackageImportPreviewRead":
        return cls(
            schema_version=value.schema_version,
            state=value.state.value,
            operation_id=value.operation_id,
            archive_digest=value.archive_digest,
            content_digest=value.content_digest,
            package_id=value.package_id,
            package_version=value.package_version,
            producer_name=value.producer_name,
            producer_version=value.producer_version,
            min_reader_version=value.min_reader_version,
            world_contract_version=value.world_contract_version,
            trust_state=value.trust_state.value,
            license=value.license,
            world_name=value.world_name,
            world_tagline=value.world_tagline,
            character_names=list(value.character_names),
            role_count=value.role_count,
            place_count=value.place_count,
            rule_count=value.rule_count,
            glossary_count=value.glossary_count,
            asset_count=value.asset_count,
            asset_bytes=value.asset_bytes,
            total_decoded_pixels=value.total_decoded_pixels,
            excluded_owner_controlled_characters=(
                value.excluded_owner_controlled_characters
            ),
            excluded_runtime_records=value.excluded_runtime_records,
            collision_plan=WorldPackageCollisionPlanRead(
                planned_world_slug=value.collision_plan.planned_world_slug,
                characters=[
                    WorldPackageCharacterCollisionRead(
                        source_ref=item.source_ref,
                        display_name=item.display_name,
                        planned_handle=item.planned_handle,
                    )
                    for item in value.collision_plan.characters
                ],
                duplicate_state=value.collision_plan.duplicate_state.value,
                commit_allowed_by_default=(
                    value.collision_plan.commit_allowed_by_default
                ),
            ),
            normalized_assets=[
                WorldPackageNormalizedAssetRead(
                    source_ref=item.source_ref,
                    normalized_ref=item.normalized_ref,
                    normalized_sha256=item.normalized_sha256,
                    normalized_bytes=item.normalized_bytes,
                    width=item.width,
                    height=item.height,
                    alt_text=item.alt_text,
                )
                for item in value.normalized_assets
            ],
            warnings=list(value.warnings),
            blocking_issues=list(value.blocking_issues),
            expires_at=value.expires_at,
        )


class WorldPackagePreparedImportPreviewRead(WorldPackageExportSchema):
    preview_token: str
    preview: WorldPackageImportPreviewRead

    @classmethod
    def from_domain(
        cls, value: WorldPackagePreparedPreview
    ) -> "WorldPackagePreparedImportPreviewRead":
        return cls(
            preview_token=value.preview_token,
            preview=WorldPackageImportPreviewRead.from_domain(value.preview),
        )


__all__ = [
    "WorldPackageExportPreviewRead",
    "WorldPackageExportRequest",
    "WorldPackageImportPreviewRead",
    "WorldPackagePreparedExportRead",
    "WorldPackagePreparedImportPreviewRead",
]
