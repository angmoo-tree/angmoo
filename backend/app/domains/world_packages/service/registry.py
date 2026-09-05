"""Lineage, version reuse and delivery admission for World Packages.

The caller owns commit/rollback. Preview may allocate and flush source identity;
only a completed browser delivery or explicit native save acknowledgment advances
the next version. Registry SQL lives in repository/registry.py.
"""
from __future__ import annotations

from datetime import timezone
from sqlalchemy.orm import Session
from app.domains.world_packages.contracts.export import (
    WorldPackageExportRegistryRecord, WorldPackageSourceIdentity, WorldPackageVersionPreview,
)
from app.domains.world_packages.contracts.seed import WorldPackageImportRegistryRecord
from app.domains.world_packages.repository.registry import WorldPackageRegistryRepository, _export_record


class SqlAlchemyWorldPackageRegistry:
    def __init__(self, db: Session) -> None:
        self._repository = WorldPackageRegistryRepository(db)

    def find_import(self, *, local_owner_id: str, idempotency_key: str) -> WorldPackageImportRegistryRecord | None:
        return self._repository.find_import(local_owner_id=local_owner_id, idempotency_key=idempotency_key)

    def import_exists(self, *, import_id: str) -> bool:
        return self._repository.import_exists(import_id=import_id)

    def list_imported_world_ids(self) -> tuple[str, ...]:
        return self._repository.list_imported_world_ids()

    def resolve_export_source(self, *, source_world_id: str) -> WorldPackageSourceIdentity:
        item = self._repository.find_source_world(source_world_id)
        if item is None:
            item = self._repository.create_source(source_world_id)
        created_at = item.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        else:
            created_at = created_at.astimezone(timezone.utc)
        return WorldPackageSourceIdentity(package_id=item.package_id, next_version=item.next_version, created_at=created_at)

    def preview_export_version(self, *, package_id: str, seed_digest: str) -> WorldPackageVersionPreview:
        existing = self._repository.find_seed_export(package_id, seed_digest)
        if existing is not None:
            return WorldPackageVersionPreview(package_version=existing.package_version, replayed_seed=True)
        source = self._repository.get_source(package_id)
        if source is None:
            raise RuntimeError("world_package_source_missing")
        return WorldPackageVersionPreview(package_version=source.next_version, replayed_seed=False)

    def record_export_delivery(self, record: WorldPackageExportRegistryRecord) -> WorldPackageExportRegistryRecord:
        existing = self._repository.find_version_export(record.package_id, record.package_version)
        if existing is not None:
            if (
                existing.seed_digest != record.seed_digest
                or existing.manifest_digest != record.manifest_digest
                or existing.source_world_id != record.source_world_id
                or existing.license_expression != record.license_expression
            ):
                raise RuntimeError("world_package_export_version_conflict")
            return _export_record(existing)
        source = self._repository.get_source(record.package_id)
        if source is None or source.source_world_id != record.source_world_id:
            raise RuntimeError("world_package_source_missing")
        if source.next_version != record.package_version:
            raise RuntimeError("world_package_export_version_conflict")
        self._repository.add_export(record, source)
        return record

    def add_import(self, record: WorldPackageImportRegistryRecord) -> None:
        self._repository.add_import(record)


__all__ = ["SqlAlchemyWorldPackageRegistry"]
