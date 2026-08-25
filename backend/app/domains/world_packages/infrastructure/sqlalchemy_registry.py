"""SQLAlchemy World Package lineage registry adapter."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.world_packages.domain.seed import (
    WorldPackageImportIdMapping,
    WorldPackageImportRegistryRecord,
)
from app.domains.world_packages.infrastructure.sqlalchemy_models import (
    WorldPackageImport,
    WorldPackageImportIdMap,
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


__all__ = ["SqlAlchemyWorldPackageRegistry"]
