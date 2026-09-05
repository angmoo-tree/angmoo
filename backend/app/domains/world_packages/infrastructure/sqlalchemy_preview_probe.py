"""Read-only SQLite collision, duplicate, and local-export trust probe."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters.public import Character
from app.domains.world_packages.utils.canonical import canonical_sha256
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
        trust_state = (
            WorldPackageTrustState.LOCALLY_EXPORTED
            if local_export is not None
            else WorldPackageTrustState.CHECKSUM_VERIFIED_UNSIGNED
        )

        imports = tuple(
            self._db.scalars(
                select(WorldPackageImport).where(
                    WorldPackageImport.package_id == package_id
                )
            )
        )
        same_version = tuple(
            item
            for item in imports
            if item.package_version == manifest.package_version
        )
        if any(
            item.content_digest != manifest.content_digest
            for item in same_version
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.TAMPERED_VERSION
            )
        if same_version:
            duplicate_state = WorldPackageDuplicateState.ALREADY_IMPORTED
        elif imports:
            duplicate_state = WorldPackageDuplicateState.INDEPENDENT_FORK
        else:
            duplicate_state = WorldPackageDuplicateState.NEW_PACKAGE

        world_slugs = frozenset(self._db.scalars(select(World.slug)))
        handles = frozenset(self._db.scalars(select(Character.handle)))
        collision_plan = plan_world_package_collisions(
            world_name=package.world.name,
            character_hints=tuple(
                (item.ref, item.display_name, item.handle_hint)
                for item in package.characters.characters
            ),
            content_digest=manifest.content_digest,
            existing_world_slugs=world_slugs,
            existing_character_handles=handles,
            duplicate_state=duplicate_state,
        )
        warnings = ["author_signature_not_available"]
        if duplicate_state is WorldPackageDuplicateState.ALREADY_IMPORTED:
            warnings.append("already_imported")
        elif duplicate_state is WorldPackageDuplicateState.INDEPENDENT_FORK:
            warnings.append("independent_fork_no_merge")
        return WorldPackagePreviewAssessment(
            trust_state=trust_state,
            collision_plan=collision_plan,
            warnings=tuple(warnings),
        )


__all__ = ["SqlAlchemyWorldPackagePreviewProbe"]
