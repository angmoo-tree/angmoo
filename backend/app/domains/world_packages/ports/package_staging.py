"""Storage-neutral staging boundary for untrusted package bytes."""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Protocol

from app.domains.world_packages.domain.import_state import WorldPackageImportState
from app.domains.world_packages.domain.preview import (
    WorldPackageImportPreview,
    WorldPackagePreparedPreview,
)


class WorldPackageStagingPort(Protocol):
    async def receive(
        self,
        *,
        operation_id: str,
        owner_id: str,
        chunks: AsyncIterable[bytes],
    ) -> None: ...

    def transition(
        self,
        *,
        operation_id: str,
        owner_id: str,
        state: WorldPackageImportState,
    ) -> None: ...

    def publish_preview(
        self,
        *,
        owner_id: str,
        preview: WorldPackageImportPreview,
    ) -> WorldPackagePreparedPreview: ...

    def read_preview(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
    ) -> WorldPackageImportPreview: ...

    def discard(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
    ) -> None: ...

    def reject(self, *, operation_id: str, owner_id: str) -> None: ...


__all__ = ["WorldPackageStagingPort"]
