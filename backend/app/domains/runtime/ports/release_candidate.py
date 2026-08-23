"""Storage-neutral ER6 backup and restore contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ReleaseCandidateBackupFile:
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ReleaseCandidateBackupManifest:
    schema_version: int
    app_version: str
    fixture_id: str
    created_at: str
    synthetic_fixture: bool
    contains_real_credentials: bool
    files: tuple[ReleaseCandidateBackupFile, ...]
    content_sha256: str


@dataclass(frozen=True)
class ReleaseCandidateBackupReport:
    manifest: ReleaseCandidateBackupManifest
    backup_root: str


@runtime_checkable
class ReleaseCandidateBackupPort(Protocol):
    def create(self, backup_root: str) -> ReleaseCandidateBackupReport: ...

    def inspect(self, backup_root: str) -> ReleaseCandidateBackupReport: ...

    def restore(
        self,
        backup_root: str,
        target_root: str,
    ) -> ReleaseCandidateBackupReport: ...


__all__ = [
    "ReleaseCandidateBackupFile",
    "ReleaseCandidateBackupManifest",
    "ReleaseCandidateBackupPort",
    "ReleaseCandidateBackupReport",
]
