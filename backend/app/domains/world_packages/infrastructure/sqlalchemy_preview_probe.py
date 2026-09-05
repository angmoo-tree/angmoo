"""Read-only SQLite collision, duplicate, and local-export trust probe."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters.public import Character
from app.domains.world_packages.utils.canonical import canonical_sha256
from app.domains.world_packages.service.preview import assess_world_package_preview
from app.domains.world_packages.policies.collision import (
    WorldPackageDuplicateState,
    plan_world_package_collisions,
)
from app.domains.world_packages.exceptions import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.constants import WorldPackageTrustState
from app.domains.world_packages.contracts.preview import (
    ValidatedWorldPackage,
    WorldPackagePreviewAssessment,
)
from app.domains.world_packages.models import (
    WorldPackageExport,
    WorldPackageImport,
)
from app.domains.worlds.public import World


class SqlAlchemyWorldPackagePreviewProbe:
    def __init__(self, db: Session) -> None:
        self._db = db

    def assess(
        self,
        *,
        local_owner_id: str,
        package: ValidatedWorldPackage,
    ) -> WorldPackagePreviewAssessment:
        del local_owner_id  # collisions are installation-wide by schema contract
        manifest = package.manifest
        package_id = str(manifest.package_id)
        manifest_digest = canonical_sha256(manifest)
        local_export = self._db.scalar(
            select(WorldPackageExport).where(
                WorldPackageExport.package_id == package_id,
                WorldPackageExport.package_version == manifest.package_version,
                WorldPackageExport.manifest_digest == manifest_digest,
            )
        )
        imports = tuple(
            self._db.execute(select(WorldPackageImport.package_version, WorldPackageImport.content_digest).where(
                WorldPackageImport.package_id == package_id,
            ))
        )
        world_slugs = frozenset(self._db.scalars(select(World.slug)))
        handles = frozenset(self._db.scalars(select(Character.handle)))
        return assess_world_package_preview(
            package=package, locally_exported=local_export is not None,
            imports=imports, world_slugs=world_slugs, handles=handles,
        )


__all__ = ["SqlAlchemyWorldPackagePreviewProbe"]
