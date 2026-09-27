"""World Package v3 manifest; previous published schemas remain frozen."""

from typing import Literal

from app.domains.world_packages.schemas.manifest_v2 import WorldPackageManifestV2


class WorldPackageManifestV3(WorldPackageManifestV2):
    format_version: Literal[3]
    schema_version: Literal["world-package-v3"]
