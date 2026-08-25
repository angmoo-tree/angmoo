"""HTTP schemas for deterministic World Package export."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.world_packages.domain.export import WorldPackageExportPreview
from app.domains.world_packages.domain.manifest import WorldPackageLicense


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


__all__ = [
    "WorldPackageExportPreviewRead",
    "WorldPackageExportRequest",
    "WorldPackagePreparedExportRead",
]
