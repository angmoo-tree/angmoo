"""Package lineage and idempotency registry boundary."""

from __future__ import annotations

from typing import Protocol

from app.domains.world_packages.domain.seed import WorldPackageImportRegistryRecord


class WorldPackageRegistryPort(Protocol):
    def find_import(
        self, *, local_owner_id: str, idempotency_key: str
    ) -> WorldPackageImportRegistryRecord | None: ...

    def add_import(self, record: WorldPackageImportRegistryRecord) -> None: ...


__all__ = ["WorldPackageRegistryPort"]
