"""Deterministic archive writer boundary."""

from __future__ import annotations

from typing import Protocol

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


__all__ = ["WorldPackageArchivePort"]
