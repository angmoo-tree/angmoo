"""Immutable manifest and consecutive migration registry for SQLite."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from sqlalchemy import Connection

from app.runtime.migrations.sqlite_versions.v1_to_v2_world_package_registry import (
    MUTABLE_IDENTITY_TABLES as V1_TO_V2_MUTABLE_TABLES,
    capture_v1_to_v2_delta,
    upgrade_v1_to_v2,
    verify_v1_to_v2_delta,
)
from app.runtime.migrations.sqlite_versions.v2_to_v3_no_specific_role import (
    MUTABLE_IDENTITY_TABLES as V2_TO_V3_MUTABLE_TABLES,
    capture_v2_to_v3_delta,
    upgrade_v2_to_v3,
    verify_v2_to_v3_delta,
)
from app.runtime.migrations.sqlite_versions.v3_to_v4_world_scoped_chat import (
    MUTABLE_IDENTITY_TABLES as V3_TO_V4_MUTABLE_TABLES,
    capture_v3_to_v4_delta,
    upgrade_v3_to_v4,
    verify_v3_to_v4_delta,
)
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationContract
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION


SqliteMigration = Callable[[Connection], None]
_MANIFEST_ROOT = Path(__file__).with_name("manifests")


class SqliteVersionContractError(RuntimeError):
    """Stable failure for a missing or drifting embedded SQLite contract."""


@dataclass(frozen=True)
class SqliteVersionManifest:
    schema_version: int
    canonical_table_count: int
    schema_digest: str
    table_inventory: tuple[str, ...]
    source_revision: str
    source_migration_count: int

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "schema_version": self.schema_version,
                    "canonical_table_count": self.canonical_table_count,
                    "schema_digest": self.schema_digest,
                    "table_inventory": list(self.table_inventory),
                    "source_revision": self.source_revision,
                    "source_migration_count": self.source_migration_count,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


MIGRATIONS: dict[int, SqliteMigration] = {
    1: upgrade_v1_to_v2,
    2: upgrade_v2_to_v3,
    3: upgrade_v3_to_v4,
}

MIGRATION_CONTRACTS: dict[int, SqliteMigrationContract] = {
    1: SqliteMigrationContract(
        source_version=1,
        target_version=2,
        name="world_package_registry",
        mutable_identity_tables=V1_TO_V2_MUTABLE_TABLES,
        capture=capture_v1_to_v2_delta,
        verify=verify_v1_to_v2_delta,
    ),
    2: SqliteMigrationContract(
        source_version=2,
        target_version=3,
        name="no_specific_role",
        mutable_identity_tables=V2_TO_V3_MUTABLE_TABLES,
        capture=capture_v2_to_v3_delta,
        verify=verify_v2_to_v3_delta,
    ),
    3: SqliteMigrationContract(
        source_version=3,
        target_version=4,
        name="world_scoped_chat",
        mutable_identity_tables=V3_TO_V4_MUTABLE_TABLES,
        capture=capture_v3_to_v4_delta,
        verify=verify_v3_to_v4_delta,
    ),
}


def migration_contract(source_version: int) -> SqliteMigrationContract:
    contract = MIGRATION_CONTRACTS.get(source_version)
    if contract is None or contract.target_version != source_version + 1:
        raise SqliteVersionContractError(
            f"sqlite_migration_contract_missing:v{source_version}_to_v{source_version + 1}"
        )
    return contract


def load_sqlite_manifest(version: int) -> SqliteVersionManifest:
    path = _MANIFEST_ROOT / f"v{version}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = SqliteVersionManifest(
            schema_version=int(payload["schema_version"]),
            canonical_table_count=int(payload["canonical_table_count"]),
            schema_digest=str(payload["schema_digest"]),
            table_inventory=tuple(str(item) for item in payload["table_inventory"]),
            source_revision=str(payload["source_revision"]),
            source_migration_count=int(payload["source_migration_count"]),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SqliteVersionContractError("sqlite_schema_manifest_missing") from exc
    if manifest.schema_version != version:
        raise SqliteVersionContractError("sqlite_schema_manifest_mismatch")
    if len(manifest.schema_digest) != 64:
        raise SqliteVersionContractError("sqlite_schema_manifest_mismatch")
    if len(manifest.table_inventory) != manifest.canonical_table_count:
        raise SqliteVersionContractError("sqlite_schema_manifest_mismatch")
    return manifest


def migration_chain(
    current_version: int,
    target_version: int = SQLITE_SCHEMA_VERSION,
) -> tuple[tuple[int, SqliteMigration], ...]:
    if current_version > target_version:
        raise SqliteVersionContractError("sqlite_schema_newer_than_runtime")
    steps: list[tuple[int, SqliteMigration]] = []
    for version in range(current_version, target_version):
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise SqliteVersionContractError(
                f"sqlite_migration_step_missing:v{version}_to_v{version + 1}"
            )
        load_sqlite_manifest(version)
        load_sqlite_manifest(version + 1)
        migration_contract(version)
        steps.append((version, migration))
    return tuple(steps)


__all__ = [
    "MIGRATIONS",
    "MIGRATION_CONTRACTS",
    "SqliteMigration",
    "SqliteVersionContractError",
    "SqliteVersionManifest",
    "load_sqlite_manifest",
    "migration_contract",
    "migration_chain",
]
