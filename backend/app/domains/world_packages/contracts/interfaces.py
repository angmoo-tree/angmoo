"""Required fake/provider/storage and same-session UoW seams for Packages.

These Protocols are shared input contracts, not a required layer per service.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from app.domains.world_packages.contracts.seed import (
    WorldPackageDestinationSeedRequest,
    WorldPackageDestinationSeedResult,
)
from app.domains.world_packages.contracts.import_commit import (
    WorldPackageImportCommitRequest,
    WorldPackageImportCommitResult,
)
from app.domains.world_packages.contracts.preview import (
    ValidatedWorldPackage,
    WorldPackagePreviewAssessment,
)
from app.domains.world_packages.contracts.export import (
    WorldPackageMediaCandidate,
    WorldPackageResolvedAssets,
)
from app.domains.world_packages.schemas.content import (
    AssetIndexDocument,
    CharactersDocument,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.contracts.export import (
    WorldPackageBuiltArchive,
    WorldPackageResolvedAssets,
    WorldPackageSourceIdentity,
)
from app.domains.world_packages.schemas.manifest import WorldPackageLicense
from collections.abc import AsyncIterable
from app.domains.world_packages.constants import WorldPackageImportState
from app.domains.world_packages.contracts.preview import (
    WorldPackageImportPreview,
    WorldPackagePreparedPreview,
)
from app.domains.world_packages.contracts.export import (
    WorldPackageExportRegistryRecord,
    WorldPackageSourceIdentity,
    WorldPackageVersionPreview,
)
from app.domains.world_packages.contracts.seed import WorldPackageImportRegistryRecord
from app.domains.world_packages.contracts.seed import WorldPackageSourceSnapshot


@runtime_checkable
class WorldPackageDestinationSeedPort(Protocol):
    def seed(
        self, request: WorldPackageDestinationSeedRequest
    ) -> WorldPackageDestinationSeedResult: ...


class WorldPackageImportCommitPort(Protocol):
    def find_replay(
        self,
        *,
        local_owner_id: str,
        idempotency_key: str,
        expected_content_digest: str,
    ) -> WorldPackageImportCommitResult | None: ...

    def execute(
        self, request: WorldPackageImportCommitRequest
    ) -> WorldPackageImportCommitResult: ...


class WorldPackageArchiveValidationPort(Protocol):
    def validate(self, *, operation_id: str) -> ValidatedWorldPackage: ...


class WorldPackagePreviewProbePort(Protocol):
    def assess(
        self,
        *,
        local_owner_id: str,
        package: ValidatedWorldPackage,
    ) -> WorldPackagePreviewAssessment: ...


class ManagedPackageAssetPort(Protocol):
    def resolve_export_assets(
        self, *, candidates: tuple[WorldPackageMediaCandidate, ...]
    ) -> WorldPackageResolvedAssets: ...





class WorldPackageArchivePort(Protocol):
    def build(
        self,
        *,
        identity: WorldPackageSourceIdentity,
        package_version: int,
        world: PortableWorldDefinition,
        characters: CharactersDocument,
        world_characters: WorldCharactersDocument,
        asset_index: AssetIndexDocument,
        resolved_assets: WorldPackageResolvedAssets,
        license: WorldPackageLicense,
        license_text: str | None,
    ) -> WorldPackageBuiltArchive: ...


class WorldPackageStagingPort(Protocol):
    async def receive(
        self,
        *,
        operation_id: str,
        owner_id: str,
        chunks: AsyncIterable[bytes],
    ) -> None: ...

    def transition(
        self,
        *,
        operation_id: str,
        owner_id: str,
        state: WorldPackageImportState,
    ) -> None: ...

    def publish_preview(
        self,
        *,
        owner_id: str,
        preview: WorldPackageImportPreview,
    ) -> WorldPackagePreparedPreview: ...

    def read_preview(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
    ) -> WorldPackageImportPreview: ...

    def begin_commit(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
        expected_content_digest: str,
    ) -> WorldPackageImportPreview: ...

    def restore_preview(self, *, operation_id: str, owner_id: str) -> None: ...

    def complete_commit(self, *, operation_id: str, owner_id: str) -> None: ...

    def discard(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
    ) -> None: ...

    def reject(self, *, operation_id: str, owner_id: str) -> None: ...


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


class WorldPackageSourceSnapshotPort(Protocol):
    def snapshot(
        self, *, source_world_id: str, local_owner_id: str
    ) -> WorldPackageSourceSnapshot: ...


@runtime_checkable
class WorldPackageSeedUnitOfWorkPort(Protocol):
    def execute(
        self, request: WorldPackageDestinationSeedRequest
    ) -> WorldPackageDestinationSeedResult: ...

__all__ = ['WorldPackageDestinationSeedPort', 'WorldPackageImportCommitPort', 'WorldPackageArchiveValidationPort', 'WorldPackagePreviewProbePort', 'ManagedPackageAssetPort', 'WorldPackageArchivePort', 'WorldPackageStagingPort', 'WorldPackageRegistryPort', 'WorldPackageSourceSnapshotPort', 'WorldPackageSeedUnitOfWorkPort']
