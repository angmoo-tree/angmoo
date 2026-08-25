"""Caller-owned destination seed boundary.

Implementations may flush, but must never commit or roll back the caller's
transaction.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domains.world_packages.domain.seed import (
    WorldPackageDestinationSeedRequest,
    WorldPackageDestinationSeedResult,
)


@runtime_checkable
class WorldPackageDestinationSeedPort(Protocol):
    def seed(
        self, request: WorldPackageDestinationSeedRequest
    ) -> WorldPackageDestinationSeedResult: ...


__all__ = ["WorldPackageDestinationSeedPort"]
