"""Public contract for World Package v1.

The public surface remains storage-neutral. PR B adds caller-owned seed and
registry contracts while routes, archive I/O, and UI remain later work.
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
    "WorldPackageContractError",
    "WorldPackageDestinationSeedRequest",
    "WorldPackageDestinationSeedResult",
    "WorldPackageEntry",
    "WorldPackageImportState",
    "WorldPackageImportIdMapping",
    "WorldPackageImportRegistryRecord",
    "WorldPackageLicense",
    "WorldPackageManifest",
    "WorldPackagePolicy",
    "WorldPackageProducer",
    "WorldPackageReasonCode",
    "WorldPackageSourceSnapshot",
    "WorldPackageTrustState",
    "canonical_entry_index_digest",
    "canonical_json_bytes",
    "canonical_sha256",
]
