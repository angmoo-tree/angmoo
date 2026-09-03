"""Generate or verify the P8-L-R Memory owner-control inventory."""

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

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-r-memory-owner-control-inventory.json"
TODAY_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-r-today-sns-activity-inventory.json"
FROZEN_OUTPUT_SHA256 = "c02287d0d563582522a58c0ca9fd217b6b6985a59eafafa7b6278b6f8a818520"
Q_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-q-memory-read-inspector-inventory.json"
Q_INVENTORY_SHA256 = "543f8f2457abbc03f50b7e0cace5fa8edffe680c74df53379fa21da588da9611"

from app.domains.memory.domain.lifecycle import (  # noqa: E402
    MAX_MEMORY_SUMMARY_LENGTH,
    MEMORY_WRITE_CONTRACT_VERSION,
)
from app.domains.memory.domain.read_surface import (  # noqa: E402
    MEMORY_READ_CONTRACT_VERSION,
)
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest  # noqa: E402
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402


class InventoryError(RuntimeError):
    pass


REQUIRED_FILES = (
    "backend/app/api/v1/routes/memory.py",
    "backend/app/domains/memory/api/schemas.py",
    "backend/app/domains/memory/application/scope_control.py",
    "backend/app/domains/memory/application/write_lifecycle.py",
    "backend/app/domains/memory/domain/lifecycle.py",
    "backend/app/domains/memory/infrastructure/repository.py",
    "backend/app/domains/memory/ports/repository.py",
    "backend/app/domains/memory/public.py",
    "backend/app/runtime/memory/recall_projection.py",
    "backend/app/runtime/persistence/sqlite_schema.py",
    "backend/security/public_route_security_inventory.json",
    "backend/security/route_security_inventory.json",
    "backend/tests/test_m3_security_harness.py",
    "backend/tests/test_p8_l_h_canonical_recall.py",
    "backend/tests/test_p8_l_q_frontend_memory.py",
    "backend/tests/test_p8_l_q_memory_read_inspector.py",
    "backend/tests/test_p8_l_r_memory_owner_control.py",
    "browser-tests/product-shell.spec.ts",
    "browser-tests/static-product-shell.spec.ts",
    "docs/architecture/backend-domains.md",
    "docs/architecture/frontend-design-reference.md",
    "docs/architecture/frontend-product-shell.md",
    "docs/architecture/p8-l-q-memory-read-inspector-inventory.json",
    "docs/architecture/p8-l-r-memory-owner-control.md",
    "frontend/DESIGN.md",
    "frontend/src/features/memory/api/memory-client.ts",
    "frontend/src/features/memory/model/memory-contract.ts",
    "frontend/src/features/memory/public.ts",
    "frontend/src/features/memory/ui/memory-workspace.module.css",
    "frontend/src/features/memory/ui/memory-workspace.tsx",
    "scripts/generate_public_route_inventory.py",
    "scripts/ci/generate_p8_l_q_memory_read_inspector_inventory.py",
    "scripts/ci/generate_p8_l_r_memory_owner_control_inventory.py",
)


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


def _forbid_text(relative: str, values: tuple[str, ...]) -> None:
    text = (ROOT / relative).read_text(encoding="utf-8")
    present = [value for value in values if value in text]
    if present:
        raise InventoryError(f"{relative}: forbidden contract present: {present}")


def _forbid_imports(relative: str, prefixes: tuple[str, ...]) -> None:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    forbidden = [
        module
        for module in imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)
    ]
    if forbidden:
        raise InventoryError(f"{relative}: forbidden imports: {forbidden}")


def _boundary_contract() -> dict[str, Any]:
    for relative in (
        "backend/app/domains/memory/domain/lifecycle.py",
        "backend/app/domains/memory/application/scope_control.py",
        "backend/app/domains/memory/application/write_lifecycle.py",
    ):
        _forbid_imports(
            relative,
            ("app.integrations", "app.runtime", "sqlalchemy", "fastapi"),
        )
    _require_text(
        "backend/app/api/v1/routes/memory.py",
        (
            '@router.put("/memory/settings"',
            '@router.put("/memories/{memory_id}/pin"',
            '"/memories/{memory_id}/corrections"',
            '@router.delete("/memories/{memory_id}"',
            "require_local_frontend_request(request, mutation=True)",
            "db.commit()",
        ),
    )
    _forbid_text(
        "backend/app/api/v1/routes/memory.py",
        ("SELECT ", "INSERT ", "UPDATE ", "DELETE FROM ", "MATCH ", "session.execute("),
    )
    _require_text(
        "backend/app/domains/memory/application/write_lifecycle.py",
        (
            "def correct_summary(",
            "memory_correction_item_id(",
            "self._source_reader.read_evidence(",
            "validate_source_digest(evidence.source_digest) != row.source_digest",
            "memory_correction_source_unavailable",
        ),
    )
    _require_text(
        "backend/app/domains/memory/infrastructure/repository.py",
        (
            "def correct_item_summary(",
            "old.status = MemoryItemStatus.SUPERSEDED.value",
            "old.superseded_by_id = replacement.id",
            "self._invalidate_hot_briefs(setting.id, now=now)",
            "self._enqueue_job(",
        ),
    )
    _require_text(
        "frontend/src/features/memory/ui/memory-workspace.tsx",
        (
            "mutationLockRef",
            "updateMemorySetting",
            "setMemoryPin",
            "correctMemoryItem",
            "deleteMemoryItem",
            "기억을 켰어요.",
            "기억을 정정했어요.",
            "기억을 삭제했어요.",
        ),
    )
    _require_text(
        "frontend/src/features/memory/api/memory-client.ts",
        (
            'method: "PUT"',
            'method: "POST"',
            'method: "DELETE"',
            'credentials: "same-origin"',
            'read.projection_cleanup !== "automatic_after_commit"',
        ),
    )
    return {
        "backend_domain_owner": "app.domains.memory",
        "frontend_feature": "frontend/src/features/memory",
        "domain_application_framework_imports": 0,
        "raw_sql_or_cypher_in_route": 0,
        "actual_identity_scope_owner": "code",
        "canonical_mutation_owner": "code",
        "projection_cleanup_owner": "after_commit_code",
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(Q_INVENTORY_PATH) != Q_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-Q predecessor digest drift")
    predecessor = json.loads(Q_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-Q":
        raise InventoryError("P8-L-Q predecessor owner drift")
    if SQLITE_SCHEMA_VERSION != 7:
        raise InventoryError("P8-L-R must not advance Embedded schema v7")
    manifest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)

    return {
        "schema_version": 1,
        "owner_stage": "P8-L-R",
        "contract_versions": {
            "memory_read": MEMORY_READ_CONTRACT_VERSION,
            "memory_write": MEMORY_WRITE_CONTRACT_VERSION,
            "owner_control_api": "memory-owner-control.v1",
        },
        "predecessor": _record(
            "docs/architecture/p8-l-q-memory-read-inspector-inventory.json"
        ),
        "historical_chain": {
            "p8_l_q_sha256": Q_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-R",
        },
        "schema": {
            "new_alembic_migration": None,
            "new_embedded_schema_version": None,
            "current_embedded_schema_version": SQLITE_SCHEMA_VERSION,
            "new_canonical_tables": [],
            "new_canonical_columns": [],
            "canonical_table_count": manifest.canonical_table_count,
            "source_revision": manifest.source_revision,
            "source_migration_count": manifest.source_migration_count,
            "new_ladybug_generation": None,
        },
        "domain_boundary": _boundary_contract(),
        "mutation_contract": {
            "routes": [
                "PUT /worlds/{world_id}/world-characters/{subject_id}/memory/settings",
                "PUT /worlds/{world_id}/world-characters/{subject_id}/memories/{memory_id}/pin",
                "POST /worlds/{world_id}/world-characters/{subject_id}/memories/{memory_id}/corrections",
                "DELETE /worlds/{world_id}/world-characters/{subject_id}/memories/{memory_id}",
            ],
            "memory_off_blocks_new_candidates_writes_and_retrieval": True,
            "memory_off_keeps_existing_items_readable": True,
            "memory_off_allows_pin_unpin_and_delete": True,
            "memory_off_allows_correction": False,
            "correction_creates_replacement": True,
            "correction_revalidates_every_evidence_source": True,
            "superseded_item_is_not_retrievable": True,
            "delete_blocks_retrieval_in_canonical_transaction": True,
            "target_state_or_key_replay_idempotent": True,
            "optimistic_version_conflict": True,
            "projection_cleanup": "automatic_after_commit",
            "canonical_commit_rolled_back_on_projection_failure": False,
            "provider_calls": 0,
        },
        "bounds": {
            "correction_summary_characters": MAX_MEMORY_SUMMARY_LENGTH,
            "simultaneous_workspace_mutations": 1,
            "narrow_browser_reflow_max_width": 799,
        },
        "frontend": {
            "canonical_route": "/memory",
            "feature_owner": "features/memory",
            "wide_window_kind": "memory",
            "next_static_same_feature": True,
            "controls": ["on_off", "pin_unpin", "correction", "delete"],
            "transient_retry_reuses_request": True,
            "version_conflict_reloads_canonical_state": True,
            "correction_delete_use_shared_dialog": True,
            "raw_projection_details_visible": False,
        },
        "executable_contract_gates": [
            "owner_world_subject_scope_isolation",
            "local_mutation_origin_required",
            "setting_target_state_idempotency_and_version_conflict",
            "pin_unpin_while_off_and_replay",
            "correction_source_revalidation_and_supersession",
            "delete_immediate_retrieval_block",
            "after_commit_projection_replacement_and_tombstone",
            "single_pending_owner_mutation",
            "same_request_transient_retry",
            "stale_conflict_reload",
            "next_static_owner_control_parity",
            "narrow_browser_reflow",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "new_memory_schema_or_migration",
            "graph_mutation",
            "provider_or_llm_call",
            "installed_runtime_user_gate",
            "held_out_causal_quality_and_latency_closeout",
            "release_or_production",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if TODAY_INVENTORY_PATH.is_file():
            if _sha256(OUTPUT_PATH) != FROZEN_OUTPUT_SHA256:
                raise InventoryError("frozen P8-L-R owner-control inventory digest drift")
            print("P8-L-R owner-control inventory is frozen by the Today SNS successor")
            return 0
        inventory = build_inventory()
        rendered = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.write:
            OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()}")
            return 0
        if not OUTPUT_PATH.is_file():
            raise InventoryError("generated P8-L-R inventory is missing")
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-R inventory drift; run python "
                "scripts/ci/generate_p8_l_r_memory_owner_control_inventory.py --write"
            )
        print("P8-L-R Memory owner-control inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-R inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
