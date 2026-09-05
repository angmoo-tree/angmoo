"""Storage-neutral staging boundary for untrusted package bytes."""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Protocol

from app.domains.world_packages.constants import WorldPackageImportState
from app.domains.world_packages.contracts.preview import (
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

    def begin_commit(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
        expected_content_digest: str,
    ) -> WorldPackageImportPreview: ...

    def restore_preview(self, *, operation_id: str, owner_id: str) -> None: ...

    def complete_commit(self, *, operation_id: str, owner_id: str) -> None: ...

    def discard(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
    ) -> None: ...

    def reject(self, *, operation_id: str, owner_id: str) -> None: ...


__all__ = ["WorldPackageStagingPort"]
