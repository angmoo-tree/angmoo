"""Public contract for World Package v1.

The public surface remains storage-neutral. PR C adds deterministic export
contracts while API and filesystem adapters remain behind the domain boundary.
"""

from app.domains.world_packages.domain.canonical import (
    canonical_entry_index_digest,
    canonical_json_bytes,
    canonical_sha256,
)
from app.domains.world_packages.domain.content import (
    AssetIndexDocument,
    AutonomousCharacterTemplate,
    CharactersDocument,
    ManagedImageAsset,
    PortableWorldCharacterSeed,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.export import (
    WorldPackageBuiltArchive,
    WorldPackageExportPreview,
    WorldPackageExportRegistryRecord,
    WorldPackageMediaCandidate,
    WorldPackageResolvedAsset,
    WorldPackageResolvedAssets,
    WorldPackageSourceIdentity,
    WorldPackageVersionPreview,
    recommended_world_package_filename,
    world_package_seed_digest,
)
from app.domains.world_packages.domain.import_state import (
    WorldPackageImportState,
    WorldPackageTrustState,
)
from app.domains.world_packages.domain.manifest import (
    WorldPackageCompatibility,
    WorldPackageEntry,
    WorldPackageLicense,
    WorldPackageManifest,
    WorldPackageProducer,
)
from app.domains.world_packages.domain.package_policy import (
    ArchiveEntryDescriptor,
    WorldPackagePolicy,
)
from app.domains.world_packages.domain.seed import (
    WorldPackageDestinationSeedRequest,
    WorldPackageDestinationSeedResult,
    WorldPackageImportIdMapping,
    WorldPackageImportRegistryRecord,
    WorldPackageSourceSnapshot,
)

__all__ = [
    "ArchiveEntryDescriptor",
    "AssetIndexDocument",
    "AutonomousCharacterTemplate",
    "CharactersDocument",
    "ManagedImageAsset",
    "PortableWorldCharacterSeed",
    "PortableWorldDefinition",
    "WorldCharactersDocument",
    "WorldPackageCompatibility",
    "WorldPackageBuiltArchive",
    "WorldPackageContractError",
    "WorldPackageDestinationSeedRequest",
    "WorldPackageDestinationSeedResult",
    "WorldPackageEntry",
    "WorldPackageExportPreview",
    "WorldPackageExportRegistryRecord",
    "WorldPackageImportState",
    "WorldPackageImportIdMapping",
    "WorldPackageImportRegistryRecord",
    "WorldPackageLicense",
    "WorldPackageManifest",
    "WorldPackageMediaCandidate",
    "WorldPackagePolicy",
    "WorldPackageProducer",
    "WorldPackageReasonCode",
    "WorldPackageResolvedAsset",
    "WorldPackageResolvedAssets",
    "WorldPackageSourceIdentity",
    "WorldPackageSourceSnapshot",
    "WorldPackageTrustState",
    "WorldPackageVersionPreview",
    "canonical_entry_index_digest",
    "canonical_json_bytes",
    "canonical_sha256",
    "recommended_world_package_filename",
    "world_package_seed_digest",
]
