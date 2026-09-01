"""Generate or verify the P8-L-G Memory write/lifecycle successor inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-g-memory-write-lifecycle-inventory.json"
SUCCESSOR_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-h-canonical-recall-inventory.json"
FROZEN_OUTPUT_SHA256 = (
    "81a4b9691434e6ccb9a9a6a04ef198b27bcab0852a9e74496000829b81598562"
)
F_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-f-canonical-memory-inventory.json"
F_INVENTORY_SHA256 = (
    "3558e78857a0095664815cb1364044e0d063115f76eed976be981cba95a96aab"
)

from app.domains.memory.domain.lifecycle import (  # noqa: E402
    MEMORY_WRITE_CONTRACT_VERSION,
)
from app.domains.memory.domain.provenance import MemorySourceTypeV1  # noqa: E402
from app.domains.memory.infrastructure.sqlalchemy_models import (  # noqa: E402
    MEMORY_SCHEMA_V1_TABLES,
)


class InventoryError(RuntimeError):
    """Stable failure for missing or drifting P8-L-G evidence."""


REQUIRED_FILES = (
    "backend/app/domains/memory/domain/lifecycle.py",
    "backend/app/domains/memory/application/write_lifecycle.py",
    "backend/app/domains/memory/ports/repository.py",
    "backend/app/domains/memory/ports/source_reader.py",
    "backend/app/domains/memory/ports/maintenance_queue.py",
    "backend/app/domains/memory/infrastructure/repository.py",
    "backend/app/runtime/memory/sqlalchemy_source_reader.py",
    "backend/app/domains/memory/infrastructure/maintenance_queue.py",
    "backend/app/domains/memory/public.py",
    "backend/tests/test_p8_l_g_memory_write_lifecycle.py",
    "docs/architecture/p8-l-g-memory-write-lifecycle.md",
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


def _fixture_contract(name: str) -> dict[str, Any]:
    path = ROOT / f"backend/tests/fixtures/core_experience/p0-contract-v1/{name}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("required_phase") != "P8":
        raise InventoryError(f"{name}: required phase drift")
    return {
        "fixture_id": value["fixture_id"],
        "expected": value["expected"],
        "sha256": _sha256(path),
    }


def _boundary_contract() -> dict[str, Any]:
    _require_text(
        "backend/app/domains/memory/application/write_lifecycle.py",
        (
            "class MemoryWriteLifecycleService",
            'return self._blocked("memory_opt_out")',
            "memory_candidate_idempotency_key",
            "normalize_memory_source_id",
            "normalize_memory_summary",
            "provider_call_count=0",
        ),
    )
    _require_text(
        "backend/app/domains/memory/infrastructure/repository.py",
        (
            "with self._session.begin_nested():",
            "self._session.add(self._new_evidence(item.id, evidence))",
            "MemoryItemStatus.SUPERSEDED.value",
            "MemoryItemStatus.DELETED.value",
            "memory_item_expired",
            'raise MemoryConflictError("memory_item_expired")',
            "_invalidate_hot_briefs",
        ),
    )
    _require_text(
        "backend/app/runtime/memory/sqlalchemy_source_reader.py",
        (
            "MemorySourceTypeV1.CHAT_MESSAGE",
            "MemorySourceTypeV1.POST",
            "MemorySourceTypeV1.RELATIONSHIP_EVENT",
            "MemorySourceTypeV1.JOINT_COMMITMENT",
            "explicit_owner_request",
            "thread.requester_id == scope.owner_id",
            "WorldCharacterFeedObservation",
            "WorldCharacterBlock",
        ),
    )
    _require_text(
        "backend/tests/test_p8_l_g_memory_write_lifecycle.py",
        (
            "test_memory_opt_out_fixture_is_an_executable_zero_write_gate",
            "test_item_and_evidence_rollback_together_on_provenance_failure",
            "test_correction_supersedes_old_item_and_delete_fixture_blocks_retrieval",
            "test_pin_bypasses_retention_then_unpin_enqueues_expiry_once",
            "test_expired_item_cannot_be_pinned_and_resurrected",
            "test_maintenance_queue_serializes_same_scope_and_fences_completion",
            "test_expired_maintenance_lease_is_fenced_before_reclaim",
            "test_owner_memory_request_requires_successful_user_message",
            "test_empty_canonical_summary_fails_closed_without_candidate",
        ),
    )
    _require_text(
        "backend/app/domains/memory/infrastructure/maintenance_queue.py",
        (
            ".with_for_update()",
            ".execution_options(populate_existing=True)",
            "def _claimable",
            'raise MemoryConflictError("memory_job_lease_conflict")',
        ),
    )
    return {
        "backend_ownership": "domains/memory",
        "canonical_source_adapter": "app.runtime.memory",
        "public_facade": "app.domains.memory.public",
        "application_service": "MemoryWriteLifecycleService",
        "provider_dependency": None,
        "ordinary_turn_provider_call_count": 0,
        "raw_sql_or_cypher_from_llm": 0,
        "canonical_transaction": [
            "memory_candidate_decision",
            "memory_item",
            "memory_item_evidence",
            "maintenance_job",
        ],
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(F_INVENTORY_PATH) != F_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-F predecessor digest drift")
    frozen = json.loads(F_INVENTORY_PATH.read_text(encoding="utf-8"))
    if frozen["owner_stage"] != "P8-L-F":
        raise InventoryError("P8-L-F predecessor owner drift")
    if frozen["schema"]["tables"] != list(MEMORY_SCHEMA_V1_TABLES):
        raise InventoryError("P8-L-G changed the frozen Memory table set")
    opt_out = _fixture_contract("memory_opt_out_blocked")
    deleted = _fixture_contract("memory_deleted_blocked")
    if (
        opt_out["expected"].get("outcome") != "rejected"
        or opt_out["expected"].get("code") != "memory_opt_out"
        or opt_out["expected"].get("writes") != []
        or opt_out["expected"].get("provider_call_count") != 0
    ):
        raise InventoryError("memory_opt_out_blocked contract drift")
    if (
        deleted["expected"].get("outcome") != "rejected"
        or deleted["expected"].get("code") != "memory_not_retrievable"
        or deleted["expected"].get("writes") != []
        or deleted["expected"].get("provider_call_count") != 0
    ):
        raise InventoryError("memory_deleted_blocked contract drift")
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-G",
        "contract_version": MEMORY_WRITE_CONTRACT_VERSION,
        "predecessor": _record(
            "docs/architecture/p8-l-f-canonical-memory-inventory.json"
        ),
        "historical_chain": {
            "p8_l_f_sha256": F_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-G",
        },
        "schema": {
            "new_tables": [],
            "new_migration": None,
            "reused_tables": list(MEMORY_SCHEMA_V1_TABLES),
        },
        "domain_boundary": _boundary_contract(),
        "eligible_source_types": [value.value for value in MemorySourceTypeV1],
        "eligibility_fail_closed": [
            "source_not_found",
            "source_identity_mismatch",
            "world_mismatch",
            "not_successful",
            "not_visible",
            "membership_inactive",
            "blocked",
            "unobserved",
            "empty_summary",
            "source_digest_conflict",
        ],
        "lifecycle": {
            "candidate": ["pending", "accepted", "rejected"],
            "item": ["active", "superseded", "deleted"],
            "correction": "new_item_plus_evidence_then_old_superseded",
            "delete": "immediate_canonical_read_block",
            "retention_days_default": 180,
            "pin_bypasses_expiry_only": True,
            "expired_item_pin_resurrection": False,
            "cleanup": "idempotent_leased_maintenance_job",
            "same_scope_serialization": True,
            "expired_or_superseded_lease_terminal_write": False,
        },
        "executable_contract_gates": [opt_out, deleted],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "fts5_projection_and_recall",
            "ladybugdb_recall",
            "retrieval_router_or_planners",
            "character_response_generation",
            "chat_send_or_streaming",
            "memory_owner_ui",
            "maintenance_llm_provider",
            "chat_after_commit_producer_and_consolidation_threshold",
        ],
    }


def _check_frozen_successor_boundary() -> None:
    """Verify immutable P8-L-G evidence after H owns shared Memory drift."""

    if _sha256(OUTPUT_PATH) != FROZEN_OUTPUT_SHA256:
        raise InventoryError("frozen P8-L-G inventory digest drift")
    inventory = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    predecessor = inventory.get("predecessor")
    if not isinstance(predecessor, dict):
        raise InventoryError("frozen P8-L-G predecessor is missing")
    predecessor_path = ROOT / str(predecessor.get("path") or "")
    if (
        not predecessor_path.is_file()
        or _sha256(predecessor_path) != predecessor.get("sha256")
    ):
        raise InventoryError("frozen P8-L-F predecessor digest drift")


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
                    "P8-L-G inventory is frozen; current-tree ownership moved to P8-L-H"
                )
            _check_frozen_successor_boundary()
            print("P8-L-G Memory inventory is frozen and chained to P8-L-H")
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
                "P8-L-G inventory drift; run python "
                "scripts/ci/generate_p8_l_g_memory_write_inventory.py --write"
            )
        print("P8-L-G Memory write/lifecycle inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-G inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
