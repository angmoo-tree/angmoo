"""Commit-owning boundary for an atomic World Package destination seed."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domains.world_packages.contracts.seed import (
    WorldPackageDestinationSeedRequest,
    WorldPackageDestinationSeedResult,
)


@runtime_checkable
class WorldPackageSeedUnitOfWorkPort(Protocol):
    def execute(
        self, request: WorldPackageDestinationSeedRequest
    ) -> WorldPackageDestinationSeedResult: ...


__all__ = ["WorldPackageSeedUnitOfWorkPort"]
