"""Read-only source snapshot boundary used by deterministic export."""

from __future__ import annotations

from typing import Protocol

from app.domains.world_packages.domain.seed import WorldPackageSourceSnapshot


class WorldPackageSourceSnapshotPort(Protocol):
    def snapshot(self, *, source_world_id: str) -> WorldPackageSourceSnapshot: ...


__all__ = ["WorldPackageSourceSnapshotPort"]
