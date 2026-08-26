"""Read-only validation and collision boundaries for import preview."""

from __future__ import annotations

from typing import Protocol

from app.domains.world_packages.domain.preview import (
    ValidatedWorldPackage,
    WorldPackagePreviewAssessment,
)


class WorldPackageArchiveValidationPort(Protocol):
    def validate(self, *, operation_id: str) -> ValidatedWorldPackage: ...


class WorldPackagePreviewProbePort(Protocol):
    def assess(
        self,
        *,
        local_owner_id: str,
        package: ValidatedWorldPackage,
    ) -> WorldPackagePreviewAssessment: ...


__all__ = [
    "WorldPackageArchiveValidationPort",
    "WorldPackagePreviewProbePort",
]
