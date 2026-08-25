"""Pure caller-owned seed and registry records for World Package v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.domains.world_packages.domain.content import (
    AutonomousCharacterTemplate,
    PortableWorldCharacterSeed,
    PortableWorldDefinition,
)
from app.domains.world_packages.domain.export import WorldPackageMediaCandidate
from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)


WorldPackageEntityKind = Literal["world", "character", "world_character", "asset"]


@dataclass(frozen=True, slots=True)
class WorldPackageImportIdMapping:
    source_ref: str
    entity_kind: WorldPackageEntityKind
    local_id: str


@dataclass(frozen=True, slots=True)
class WorldPackageDestinationSeedRequest:
    local_owner_id: str
    idempotency_key: str
    package_id: str
    package_version: int
    content_digest: str
    trust_state: str
    license_expression: str
    world: PortableWorldDefinition
    characters: tuple[AutonomousCharacterTemplate, ...]
    world_characters: tuple[PortableWorldCharacterSeed, ...]


@dataclass(frozen=True, slots=True)
class WorldPackageDestinationSeedResult:
    import_id: str
    imported_world_id: str
    id_mappings: tuple[WorldPackageImportIdMapping, ...]
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class WorldPackageSourceSnapshot:
    source_world_id: str
    source_fingerprint: str
    world: PortableWorldDefinition
    characters: tuple[AutonomousCharacterTemplate, ...]
    world_characters: tuple[PortableWorldCharacterSeed, ...]
    media_candidates: tuple[WorldPackageMediaCandidate, ...] = ()
    excluded_owner_controlled_characters: int = 0


@dataclass(frozen=True, slots=True)
class WorldPackageImportRegistryRecord:
    import_id: str
    local_owner_id: str
    package_id: str
    package_version: int
    content_digest: str
    imported_world_id: str
    import_mode: str
    trust_state: str
    license_expression: str
    idempotency_key: str
    id_mappings: tuple[WorldPackageImportIdMapping, ...]


def resolve_world_package_import_replay(
    request: WorldPackageDestinationSeedRequest,
    record: WorldPackageImportRegistryRecord,
) -> WorldPackageDestinationSeedResult:
    if (
        record.package_id != request.package_id
        or record.package_version != request.package_version
        or record.content_digest != request.content_digest
    ):
        raise WorldPackageContractError(WorldPackageReasonCode.COMMIT_CONFLICT)
    return WorldPackageDestinationSeedResult(
        import_id=record.import_id,
        imported_world_id=record.imported_world_id,
        id_mappings=record.id_mappings,
        replayed=True,
    )


__all__ = [
    "WorldPackageDestinationSeedRequest",
    "WorldPackageDestinationSeedResult",
    "WorldPackageEntityKind",
    "WorldPackageImportIdMapping",
    "WorldPackageImportRegistryRecord",
    "WorldPackageSourceSnapshot",
    "resolve_world_package_import_replay",
]
