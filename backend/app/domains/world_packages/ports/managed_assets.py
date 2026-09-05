"""Managed media boundary for package assets.

Export resolution is implemented. Canonical import promotion remains behind
the PR E commit boundary; PR D only normalizes assets inside runtime staging.
"""

from __future__ import annotations

from typing import Protocol

from app.domains.world_packages.contracts.export import (
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
