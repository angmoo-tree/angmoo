"""Generate or verify the append-only P8-L-F canonical Memory inventory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-f-canonical-memory-inventory.json"
SUCCESSOR_INVENTORY_PATH = (
    ROOT / "docs/architecture/p8-l-g-memory-write-lifecycle-inventory.json"
)
FROZEN_OUTPUT_SHA256 = (
    "3558e78857a0095664815cb1364044e0d063115f76eed976be981cba95a96aab"
)
E_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-e-world-social-chat-entry-inventory.json"
E_INVENTORY_SHA256 = (
    "8f40f852077d32f77f1a417c9726e08d02041aa0d0fb6223ade13049e3777a79"
)

from app import models as _models  # noqa: E402,F401 - register canonical metadata
from app.core.db import Base  # noqa: E402
from app.domains.memory.domain.provenance import MemoryKindV1  # noqa: E402
from app.domains.memory.infrastructure.sqlalchemy_models import (  # noqa: E402
    MEMORY_SCHEMA_V1_TABLES,
)
from app.runtime.migrations.sqlite_versions.registry import (  # noqa: E402
    MIGRATION_CONTRACTS,
    load_sqlite_manifest,
)
from app.runtime.persistence.sqlite_schema import (  # noqa: E402
    EXPECTED_CANONICAL_TABLE_COUNT,
    MEMORY_V5_TABLES,
    SOURCE_ALEMBIC_MIGRATION_COUNT,
    SOURCE_ALEMBIC_REVISION,
    SQLITE_SCHEMA_VERSION,
)


class InventoryError(RuntimeError):
    """Stable failure for a missing or drifting P8-L-F invariant."""


REQUIRED_FILES = (
    "backend/app/domains/memory/public.py",
    "backend/app/domains/memory/domain/provenance.py",
    "backend/app/domains/memory/domain/retention.py",
    "backend/app/domains/memory/domain/scope.py",
    "backend/app/domains/memory/ports/repository.py",
    "backend/app/domains/memory/ports/source_reader.py",
    "backend/app/domains/memory/ports/maintenance_queue.py",
    "backend/app/domains/memory/infrastructure/sqlalchemy_models.py",
    "backend/app/domains/memory/infrastructure/repository.py",
    "backend/app/alembic/versions/20260831_0085_canonical_memory_schema.py",
    "backend/app/runtime/migrations/sqlite_versions/v4_to_v5_canonical_memory.py",
    "backend/app/runtime/migrations/sqlite_versions/manifests/v5.json",
    "backend/tests/test_p8_l_f_memory_domain.py",
    "backend/tests/test_p8_l_f_memory_migration.py",
)


EXPECTED_COLUMNS = {
    "memory_scope_settings": (
        "id",
        "owner_id",
        "world_id",
        "subject_world_character_id",
        "enabled",
        "retention_days",
        "provider_mode",
        "version",
        "created_at",
        "updated_at",
    ),
    "memory_candidates": (
        "id",
        "scope_setting_id",
        "source_type",
        "source_id",
        "source_digest",
        "memory_kind_hint",
        "status",
        "reason_code",
        "idempotency_key",
        "version",
        "created_at",
        "decided_at",
    ),
    "memory_items": (
        "id",
        "owner_id",
        "world_id",
        "subject_world_character_id",
        "counterpart_world_character_id",
        "thread_id",
        "memory_kind",
        "summary",
        "status",
        "confidence",
        "salience",
        "valid_from",
        "valid_until",
        "pinned_at",
        "superseded_by_id",
        "deleted_at",
        "version",
        "created_at",
        "updated_at",
    ),
    "memory_item_evidence": (
        "id",
        "memory_item_id",
        "source_type",
        "source_id",
        "source_event_id",
        "source_world_id",
        "actor_world_character_id",
        "target_world_character_id",
        "observation_id",
        "source_created_at",
        "source_digest",
        "created_at",
    ),
    "memory_hot_briefs": (
        "id",
        "scope_setting_id",
        "summary",
        "generation",
        "source_item_high_watermark",
        "source_item_set_digest",
        "contract_version",
        "status",
        "generated_at",
        "superseded_at",
    ),
    "memory_hot_brief_items": (
        "brief_id",
        "memory_item_id",
        "memory_item_version",
    ),
    "memory_maintenance_jobs": (
        "id",
        "scope_setting_id",
        "reason",
        "idempotency_key",
        "status",
        "attempt_count",
        "lease_token",
        "lease_expires_at",
        "last_error_code",
        "created_at",
        "started_at",
        "completed_at",
    ),
}


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(_normalized_bytes(path)).hexdigest()


def _record(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file():
        raise InventoryError(f"required file is missing: {relative}")
    data = _normalized_bytes(path)
    return {
        "path": relative,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def _require_text(relative: str, values: tuple[str, ...]) -> None:
    text = (ROOT / relative).read_text(encoding="utf-8")
    missing = [value for value in values if value not in text]
    if missing:
        raise InventoryError(f"{relative}: required contract missing: {missing}")


def _supported_source_versions() -> tuple[int, ...]:
    path = ROOT / "scripts/ci/build_windows_installer_supported_upgrade_fixture.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name)
            and target.id == "SUPPORTED_SOURCE_VERSIONS"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            return tuple(int(item) for item in value)
    raise InventoryError("supported predecessor assignment is missing")


def _schema_contract() -> dict[str, Any]:
    if tuple(MEMORY_SCHEMA_V1_TABLES) != tuple(MEMORY_V5_TABLES):
        raise InventoryError("Memory schema/runtime table inventory mismatch")
    actual_columns: dict[str, list[str]] = {}
    constraints: dict[str, list[str]] = {}
    for table_name, expected in EXPECTED_COLUMNS.items():
        table = Base.metadata.tables[table_name]
        columns = tuple(column.name for column in table.columns)
        if columns != expected:
            raise InventoryError(f"{table_name}: column contract drift")
        actual_columns[table_name] = list(columns)
        constraints[table_name] = sorted(
            constraint.name
            for constraint in table.constraints
            if constraint.name is not None
        )
    required_constraints = {
        "ck_memory_scope_settings_provider_mode",
        "uq_memory_scope_settings_scope",
        "ck_memory_items_kind",
        "ck_memory_items_lifecycle",
        "ck_memory_items_counterpart_required",
        "ck_memory_items_thread_required",
        "uq_memory_item_evidence_source",
        "uq_memory_hot_briefs_scope_generation",
        "ck_memory_maintenance_jobs_lease_pair",
        "uq_memory_maintenance_jobs_scope_idempotency",
    }
    actual_constraint_names = {
        name for values in constraints.values() for name in values
    }
    if not required_constraints <= actual_constraint_names:
        raise InventoryError("Memory DB constraint contract drift")
    return {
        "tables": list(MEMORY_SCHEMA_V1_TABLES),
        "columns": actual_columns,
        "named_constraints": constraints,
        "default_enabled": False,
        "default_retention_days": 180,
        "scope": ["owner_id", "world_id", "subject_world_character_id"],
        "monotonic_version_tables": [
            "memory_scope_settings",
            "memory_candidates",
            "memory_items",
        ],
    }


def _migration_contract() -> dict[str, Any]:
    if (
        SQLITE_SCHEMA_VERSION != 5
        or SOURCE_ALEMBIC_REVISION != "20260831_0085"
        or SOURCE_ALEMBIC_MIGRATION_COUNT != 84
        or EXPECTED_CANONICAL_TABLE_COUNT != 94
    ):
        raise InventoryError("latest SQLite canonical constants drift")
    manifest = load_sqlite_manifest(5)
    contract = MIGRATION_CONTRACTS.get(4)
    if contract is None:
        raise InventoryError("v4 to v5 migration contract missing")
    if contract.mutable_identity_tables != frozenset(MEMORY_SCHEMA_V1_TABLES):
        raise InventoryError("v4 to v5 expected-delta table set drift")
    _require_text(
        "backend/app/alembic/versions/20260831_0085_canonical_memory_schema.py",
        ('revision: str = "20260831_0085"', 'down_revision: str | None = "20260831_0084"'),
    )
    return {
        "alembic_revision": "20260831_0085",
        "alembic_down_revision": "20260831_0084",
        "embedded_sqlite": {
            "schema_version": manifest.schema_version,
            "canonical_table_count": manifest.canonical_table_count,
            "schema_digest": manifest.schema_digest,
            "source_revision": manifest.source_revision,
            "source_migration_count": manifest.source_migration_count,
        },
        "migration_registry_step": "v4_to_v5_canonical_memory",
        "mutable_identity_tables": sorted(contract.mutable_identity_tables),
        "copy_on_write": True,
    }


def _boundary_contract() -> dict[str, Any]:
    _require_text(
        "backend/app/domains/memory/public.py",
        (
            "MemoryScopeService",
            "MemoryRepositoryPort",
            "MemorySourceEvidenceReaderPort",
            "MemoryMaintenanceQueuePort",
            "MemoryKindV1",
        ),
    )
    _require_text(
        "backend/app/domains/memory/infrastructure/repository.py",
        (
            "enabled=False",
            "worlds.c.owner_user_id == scope.owner_id",
            'world_characters.c.status == "active"',
            "MemoryScopeSettingModel.version == expected_version",
        ),
    )
    return {
        "backend_ownership": "domains/memory",
        "public_facade": "app.domains.memory.public",
        "ports": [
            "MemoryRepositoryPort",
            "MemorySourceEvidenceReaderPort",
            "MemoryMaintenanceQueuePort",
        ],
        "provider_calls": 0,
        "raw_sql_or_cypher_from_llm": 0,
    }


def _installer_contract() -> dict[str, Any]:
    supported = _supported_source_versions()
    if supported != (1, 2, 3, 4):
        raise InventoryError("real installer predecessor matrix is incomplete")
    _require_text(
        ".github/workflows/windows-installer.yml",
        (
            "--source-version 4",
            "supported-v4.zip",
            "-SupportedV4FixtureArchive",
        ),
    )
    _require_text(
        "scripts/ci/run_windows_installer_supported_upgrade.ps1",
        ("SupportedV4FixtureArchive", "v4 -> v5 Memory"),
    )
    return {
        "supported_predecessors": list(supported),
        "required_new_predecessor": 4,
        "hosted_workflow_archive": "supported-v4.zip",
        "idempotent_target_reinstall_required": True,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(E_INVENTORY_PATH) != E_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-E inventory digest drift")
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-F",
        "predecessor": _record(
            "docs/architecture/p8-l-e-world-social-chat-entry-inventory.json"
        ),
        "historical_chain": {
            "p8_l_e_sha256": E_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-F",
        },
        "domain_boundary": _boundary_contract(),
        "memory_kind_v1": [kind.value for kind in MemoryKindV1],
        "schema": _schema_contract(),
        "migration": _migration_contract(),
        "installer_upgrade": _installer_contract(),
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "candidate_provider",
            "candidate_eligibility_and_write",
            "fts5_retrieval",
            "graph_retrieval",
            "chat_generation",
            "memory_owner_ui",
        ],
    }


def _check_frozen_successor_boundary() -> None:
    """Verify immutable P8-L-F evidence after G owns Memory source drift."""

    if _sha256(OUTPUT_PATH) != FROZEN_OUTPUT_SHA256:
        raise InventoryError("frozen P8-L-F inventory digest drift")
    inventory = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    predecessor = inventory.get("predecessor")
    if not isinstance(predecessor, dict):
        raise InventoryError("frozen P8-L-F predecessor is missing")
    predecessor_path = ROOT / str(predecessor.get("path") or "")
    if (
        not predecessor_path.is_file()
        or _sha256(predecessor_path) != predecessor.get("sha256")
    ):
        raise InventoryError("frozen P8-L-E predecessor digest drift")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if SUCCESSOR_INVENTORY_PATH.is_file():
            if args.write:
                raise InventoryError(
                    "P8-L-F inventory is frozen; current-tree ownership moved to P8-L-G"
                )
            _check_frozen_successor_boundary()
            print("P8-L-F Memory inventory is frozen and chained to P8-L-G")
            return 0
        inventory = build_inventory()
        rendered = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.write:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()}")
            return 0
        if not OUTPUT_PATH.is_file():
            raise InventoryError(
                f"generated inventory is missing: {OUTPUT_PATH.relative_to(ROOT)}"
            )
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-F inventory drift; run python "
                "scripts/ci/generate_p8_l_f_memory_inventory.py --write"
            )
        print("P8-L-F canonical Memory inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-F inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
