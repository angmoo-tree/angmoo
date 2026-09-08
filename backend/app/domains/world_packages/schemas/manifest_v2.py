"""Versioned manifest for expanded, lossless character persona payloads."""

from typing import Literal
from pydantic import Field, model_validator
from app.domains.world_packages.schemas.manifest import WorldPackageEntry, WorldPackageManifest


class WorldPackageEntryV2(WorldPackageEntry):
    bytes: int = Field(ge=0, le=32 * 1024 * 1024)

    @model_validator(mode="after")
    def entry_budget(self):
        if self.path != "content/characters.json" and self.bytes > 5 * 1024 * 1024:
            raise ValueError("Only character content has the expanded byte budget")
        return self


class WorldPackageManifestV2(WorldPackageManifest):
    format_version: Literal[2]
    schema_version: Literal["world-package-v2"]
    entries: list[WorldPackageEntryV2] = Field(min_length=4, max_length=255)
