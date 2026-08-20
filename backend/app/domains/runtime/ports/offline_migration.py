"""Storage-neutral contracts for an offline canonical-store migration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class OfflineMigrationTableParity:
    table_name: str
    primary_key_columns: tuple[str, ...]
    row_count: int
    primary_key_sha256: str
    row_sha256: str


@dataclass(frozen=True)
class OfflineMigrationManifest:
    manifest_version: str
    app_version: str
    created_at: str
    source_dialect: str
    source_revision: str
    source_migration_count: int
    source_lineage_sha256: str
    source_schema_sha256: str
    target_schema_version: int
    target_schema_sha256: str
    conversion_inventory_sha256: str
    media_audit: str
    tables: tuple[OfflineMigrationTableParity, ...]
    content_sha256: str


@dataclass(frozen=True)
class OfflineMigrationReport:
    manifest: OfflineMigrationManifest
    manifest_path: str
    target_database_path: str
    foreign_key_violation_count: int
    integrity_check: str
    source_read_only: bool
    production_switched: bool


@runtime_checkable
class OfflineCanonicalMigrationPort(Protocol):
    def dry_run(self) -> OfflineMigrationReport: ...


__all__ = [
    "OfflineCanonicalMigrationPort",
    "OfflineMigrationManifest",
    "OfflineMigrationReport",
    "OfflineMigrationTableParity",
]
