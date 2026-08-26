"""SQLAlchemy World Package lineage registry adapter."""

from __future__ import annotations

from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.world_packages.domain.seed import (
    WorldPackageImportIdMapping,
    WorldPackageImportRegistryRecord,
)
from app.domains.world_packages.domain.export import (
    WorldPackageExportRegistryRecord,
    WorldPackageSourceIdentity,
    WorldPackageVersionPreview,
)
from app.domains.world_packages.infrastructure.sqlalchemy_models import (
    WorldPackageExport,
    WorldPackageImport,
    WorldPackageImportIdMap,
    WorldPackageSource,
)


class SqlAlchemyWorldPackageRegistry:
    def __init__(self, db: Session) -> None:
        self._db = db

    def find_import(
        self, *, local_owner_id: str, idempotency_key: str
    ) -> WorldPackageImportRegistryRecord | None:
        item = self._db.scalar(
            select(WorldPackageImport).where(
                WorldPackageImport.local_owner_id == local_owner_id,
                WorldPackageImport.idempotency_key == idempotency_key,
            )
        )
        if item is None:
            return None
        mappings = tuple(
            WorldPackageImportIdMapping(
                source_ref=row.source_ref,
                entity_kind=row.entity_kind,
                local_id=row.local_id,
            )
            for row in self._db.scalars(
                select(WorldPackageImportIdMap)
                .where(WorldPackageImportIdMap.import_id == item.import_id)
                .order_by(WorldPackageImportIdMap.source_ref)
            )
        )
        return WorldPackageImportRegistryRecord(
            import_id=item.import_id,
            local_owner_id=item.local_owner_id,
            package_id=item.package_id,
            package_version=item.package_version,
            content_digest=item.content_digest,
            imported_world_id=item.imported_world_id,
            import_mode=item.import_mode,
            trust_state=item.trust_state,
            license_expression=item.license_expression,
            idempotency_key=item.idempotency_key,
            id_mappings=mappings,
        )

    def import_exists(self, *, import_id: str) -> bool:
        return self._db.get(WorldPackageImport, import_id) is not None

    def resolve_export_source(
        self, *, source_world_id: str
    ) -> WorldPackageSourceIdentity:
        item = self._db.scalar(
            select(WorldPackageSource).where(
                WorldPackageSource.source_world_id == source_world_id
            )
        )
        if item is None:
            item = WorldPackageSource(
                package_id=uuid7_string(),
                source_world_id=source_world_id,
                next_version=1,
            )
            self._db.add(item)
            self._db.flush()
            self._db.refresh(item)
        created_at = item.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        else:
            created_at = created_at.astimezone(timezone.utc)
        return WorldPackageSourceIdentity(
            package_id=item.package_id,
            next_version=item.next_version,
            created_at=created_at,
        )

    def preview_export_version(
        self, *, package_id: str, seed_digest: str
    ) -> WorldPackageVersionPreview:
        existing = self._db.scalar(
            select(WorldPackageExport).where(
                WorldPackageExport.package_id == package_id,
                WorldPackageExport.seed_digest == seed_digest,
            )
        )
        if existing is not None:
            return WorldPackageVersionPreview(
                package_version=existing.package_version,
                replayed_seed=True,
            )
        source = self._db.get(WorldPackageSource, package_id)
        if source is None:
            raise RuntimeError("world_package_source_missing")
        return WorldPackageVersionPreview(
            package_version=source.next_version,
            replayed_seed=False,
        )

    def record_export_delivery(
        self, record: WorldPackageExportRegistryRecord
    ) -> WorldPackageExportRegistryRecord:
        existing = self._db.scalar(
            select(WorldPackageExport).where(
                WorldPackageExport.package_id == record.package_id,
                WorldPackageExport.package_version == record.package_version,
            )
        )
        if existing is not None:
            if (
                existing.seed_digest != record.seed_digest
                or existing.manifest_digest != record.manifest_digest
                or existing.source_world_id != record.source_world_id
                or existing.license_expression != record.license_expression
            ):
                raise RuntimeError("world_package_export_version_conflict")
            return _export_record(existing)

        source = self._db.get(WorldPackageSource, record.package_id)
        if source is None or source.source_world_id != record.source_world_id:
            raise RuntimeError("world_package_source_missing")
        if source.next_version != record.package_version:
            raise RuntimeError("world_package_export_version_conflict")
        row = WorldPackageExport(
            export_id=record.export_id,
            package_id=record.package_id,
            package_version=record.package_version,
            source_world_id=record.source_world_id,
            seed_digest=record.seed_digest,
            manifest_digest=record.manifest_digest,
            license_expression=record.license_expression,
            delivery_mode=record.delivery_mode,
            delivered_at=record.delivered_at,
        )
        self._db.add(row)
        source.next_version += 1
        self._db.flush()
        return record

    def add_import(self, record: WorldPackageImportRegistryRecord) -> None:
        self._db.add(
            WorldPackageImport(
                import_id=record.import_id,
                local_owner_id=record.local_owner_id,
                package_id=record.package_id,
                package_version=record.package_version,
                content_digest=record.content_digest,
                imported_world_id=record.imported_world_id,
                import_mode=record.import_mode,
                trust_state=record.trust_state,
                license_expression=record.license_expression,
                idempotency_key=record.idempotency_key,
            )
        )
        self._db.flush()

        self._db.add_all(
            [
                WorldPackageImportIdMap(
                    id=uuid7_string(),
                    import_id=record.import_id,
                    source_ref=mapping.source_ref,
                    entity_kind=mapping.entity_kind,
                    local_id=mapping.local_id,
                )
                for mapping in record.id_mappings
            ]
        )
        self._db.flush()


def _export_record(item: WorldPackageExport) -> WorldPackageExportRegistryRecord:
    delivered_at = item.delivered_at
    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(tzinfo=timezone.utc)
    return WorldPackageExportRegistryRecord(
        export_id=item.export_id,
        package_id=item.package_id,
        package_version=item.package_version,
        source_world_id=item.source_world_id,
        seed_digest=item.seed_digest,
        manifest_digest=item.manifest_digest,
        license_expression=item.license_expression,
        delivery_mode=item.delivery_mode,
        delivered_at=delivered_at,
    )


__all__ = ["SqlAlchemyWorldPackageRegistry"]
