"""Public contract for World Package v1.

PR A intentionally exports only pure contract types and deterministic helpers.
Routes, persistence, archive I/O, and provider integrations arrive behind this
boundary in later, separately reviewed pull requests.
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
    "WorldPackageEntry",
    "WorldPackageImportState",
    "WorldPackageLicense",
    "WorldPackageManifest",
    "WorldPackagePolicy",
    "WorldPackageProducer",
    "WorldPackageReasonCode",
    "WorldPackageTrustState",
    "canonical_entry_index_digest",
    "canonical_json_bytes",
    "canonical_sha256",
]
