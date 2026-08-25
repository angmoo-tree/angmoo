"""Managed media boundary for package assets.

PR B freezes ownership only. Archive extraction and filesystem promotion are
implemented by later PRs.
"""

from __future__ import annotations

from typing import Protocol

from app.domains.world_packages.domain.export import (
    WorldPackageMediaCandidate,
    WorldPackageResolvedAssets,
)


class ManagedPackageAssetPort(Protocol):
    def resolve_export_assets(
        self, *, candidates: tuple[WorldPackageMediaCandidate, ...]
    ) -> WorldPackageResolvedAssets: ...

    def stage_verified_asset(
        self, *, content: bytes, sha256: str, media_type: str
    ) -> str: ...

    def promote_staged_assets(self, *, import_id: str) -> tuple[str, ...]: ...

    def discard_staged_assets(self, *, import_id: str) -> None: ...


__all__ = ["ManagedPackageAssetPort"]
