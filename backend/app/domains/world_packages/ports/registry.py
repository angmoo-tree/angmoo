"""Package lineage and idempotency registry boundary."""

from __future__ import annotations

from typing import Protocol

from app.domains.world_packages.domain.export import (
    WorldPackageExportRegistryRecord,
    WorldPackageSourceIdentity,
    WorldPackageVersionPreview,
)
from app.domains.world_packages.domain.seed import WorldPackageImportRegistryRecord


class WorldPackageRegistryPort(Protocol):
    def resolve_export_source(
        self, *, source_world_id: str
    ) -> WorldPackageSourceIdentity: ...

    def preview_export_version(
        self, *, package_id: str, seed_digest: str
    ) -> WorldPackageVersionPreview: ...

    def record_export_delivery(
        self, record: WorldPackageExportRegistryRecord
    ) -> WorldPackageExportRegistryRecord: ...

    def find_import(
        self, *, local_owner_id: str, idempotency_key: str
    ) -> WorldPackageImportRegistryRecord | None: ...

    def add_import(self, record: WorldPackageImportRegistryRecord) -> None: ...


__all__ = ["WorldPackageRegistryPort"]
