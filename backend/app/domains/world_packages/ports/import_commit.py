"""Commit-owning boundary for canonical World Package import."""

from __future__ import annotations

from typing import Protocol

from app.domains.world_packages.domain.import_commit import (
    WorldPackageImportCommitRequest,
    WorldPackageImportCommitResult,
)


class WorldPackageImportCommitPort(Protocol):
    def find_replay(
        self,
        *,
        local_owner_id: str,
        idempotency_key: str,
        expected_content_digest: str,
    ) -> WorldPackageImportCommitResult | None: ...

    def execute(
        self, request: WorldPackageImportCommitRequest
    ) -> WorldPackageImportCommitResult: ...


__all__ = ["WorldPackageImportCommitPort"]
