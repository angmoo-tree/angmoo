"""Storage-neutral records for digest-bound World Package import commit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.domains.world_packages.contracts.preview import (
    ValidatedWorldPackage,
    WorldPackageImportPreview,
)


WorldPackageDuplicateStrategy = Literal["reject", "independent_copy"]


@dataclass(frozen=True, slots=True)
class WorldPackageImportCommitRequest:
    local_owner_id: str
    idempotency_key: str
    duplicate_strategy: WorldPackageDuplicateStrategy
    approved_preview: WorldPackageImportPreview
    package: ValidatedWorldPackage


@dataclass(frozen=True, slots=True)
class WorldPackageImportCommitResult:
    import_id: str
    imported_world_id: str
    device_home_world_id: str
    replayed: bool = False


__all__ = [
    "WorldPackageDuplicateStrategy",
    "WorldPackageImportCommitRequest",
    "WorldPackageImportCommitResult",
]
