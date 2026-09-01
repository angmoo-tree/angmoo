"""Generate or verify the P8-L-H canonical read and FTS5 recall inventory."""

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

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-h-canonical-recall-inventory.json"
SUCCESSOR_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-i-graph-recall-inventory.json"
FROZEN_OUTPUT_SHA256 = (
    "1228178d70130040b453296c1ac71fcdd1b26b0347c0c7a0eb91d05d47e8ad48"
)
G_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-g-memory-write-lifecycle-inventory.json"
G_INVENTORY_SHA256 = (
    "81a4b9691434e6ccb9a9a6a04ef198b27bcab0852a9e74496000829b81598562"
)

from app.domains.memory.domain.recall import (  # noqa: E402
    CanonicalRecallOperation,
    MEMORY_RECALL_CONTRACT_VERSION,
    MEMORY_RECALL_GENERATION,
    MEMORY_RECALL_SCHEMA_VERSION,
)
from app.domains.memory.infrastructure.sqlalchemy_models import (  # noqa: E402
    MEMORY_SCHEMA_V1_TABLES,
)


class InventoryError(RuntimeError):
    """Stable failure for missing or drifting P8-L-H evidence."""


REQUIRED_FILES = (
    "backend/app/domains/memory/domain/recall.py",
    "backend/app/domains/memory/application/recall.py",
    "backend/app/domains/memory/ports/recall.py",
    "backend/app/domains/memory/public.py",
    "backend/app/runtime/memory/sqlite_fts5_recall.py",
    "backend/app/runtime/memory/sqlalchemy_recall.py",
    "backend/app/runtime/memory/recall_projection.py",
    "backend/app/runtime/configuration.py",
    "backend/app/public_main.py",
    "backend/tests/test_p8_l_h_canonical_recall.py",
    "docs/architecture/p8-l-h-canonical-recall.md",
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


def _boundary_contract() -> dict[str, Any]:
    _require_text(
        "backend/app/domains/memory/application/recall.py",
        (
            "CANONICAL_PRIMITIVE_REGISTRY",
            "class CanonicalRecallValidator",
            "class CanonicalRecallService",
            "memory_recall_projection_unavailable",
            "memory_opt_out",
            "revalidate_candidates",
        ),
    )
    _require_text(
        "backend/app/runtime/memory/sqlite_fts5_recall.py",
        (
            '"memory-recall"',
            '"angmoo-memory-recall.sqlite3"',
            "memory_recall_fts",
            "def rebuild(",
            "def rollback(",
            "def tombstone_memory_item(",
            "def doctor(",
            "CJK bigram",
        ),
    )
    _require_text(
        "backend/app/runtime/memory/sqlalchemy_recall.py",
        (
            "class SqlAlchemyMemoryRecallDocumentSource",
            "class SqlAlchemyCanonicalRecallRepository",
            "canonical.source_digest != evidence.source_digest",
            "not canonical.visible",
            "not canonical.observed_by_subject",
            "canonical.blocked",
            "MemoryItemStatus.ACTIVE.value",
        ),
    )
    _require_text(
        "backend/app/runtime/memory/recall_projection.py",
        (
            "class EmbeddedMemoryRecallProjection",
            'event.listen(self._factory, "after_commit"',
            "MemoryRecallProjectionState.DEGRADED",
            "cannot roll back the already successful Memory transaction",
            "tombstone_scope",
        ),
    )
    _require_text(
        "backend/tests/test_p8_l_h_canonical_recall.py",
        (
            "test_private_index_is_separate_scoped_cjk_safe_and_rollbackable",
            "test_canonical_service_revalidates_stale_fts_candidates_and_memory_off",
            "test_after_commit_projection_tombstones_off_and_ignores_rollback",
            "test_typed_registry_is_closed_and_validator_rejects_unbounded_input",
        ),
    )
    return {
        "backend_ownership": "domains/memory",
        "public_facade": "app.domains.memory.public",
        "runtime_projection": "app.runtime.memory",
        "provider_dependency": None,
        "planner_call_count": 0,
        "response_generator_call_count": 0,
        "raw_sql_or_cypher_from_llm": 0,
        "canonical_schema_changed": False,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(G_INVENTORY_PATH) != G_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-G predecessor digest drift")
    predecessor = json.loads(G_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-G":
        raise InventoryError("P8-L-G predecessor owner drift")
    if predecessor["schema"]["reused_tables"] != list(MEMORY_SCHEMA_V1_TABLES):
        raise InventoryError("P8-L-H changed the frozen canonical Memory table set")
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-H",
        "contract_version": MEMORY_RECALL_CONTRACT_VERSION,
        "predecessor": _record(
            "docs/architecture/p8-l-g-memory-write-lifecycle-inventory.json"
        ),
        "historical_chain": {
            "p8_l_g_sha256": G_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-H",
        },
        "canonical_schema": {
            "new_tables": [],
            "new_migration": None,
            "reused_tables": list(MEMORY_SCHEMA_V1_TABLES),
        },
        "private_projection": {
            "generation": MEMORY_RECALL_GENERATION,
            "schema_version": MEMORY_RECALL_SCHEMA_VERSION,
            "relative_path": (
                "search/memory-recall/generations/v1/"
                "angmoo-memory-recall.sqlite3"
            ),
            "canonical": False,
            "encrypted_secret_material": False,
            "startup_rebuild": True,
            "staging_verify_atomic_promote": True,
            "rollback_image_count": 1,
            "after_commit_sync": True,
            "failed_projection_rolls_back_canonical_write": False,
            "tombstones": True,
            "doctor": True,
            "tokenizer": (
                "unicode61 + CJK bigram terms + normalized substring fallback"
            ),
        },
        "p5_feed_index": {
            "relative_path": "search/generations/v1/angmoo-search.sqlite3",
            "schema_changed": False,
            "document_loss_allowed": 0,
        },
        "domain_boundary": _boundary_contract(),
        "typed_operations": [value.value for value in CanonicalRecallOperation],
        "scope": [
            "owner_id",
            "world_id",
            "subject_world_character_id",
            "counterpart_world_character_id_optional",
            "thread_id_optional",
        ],
        "canonical_revalidation": [
            "memory_enabled",
            "active_not_deleted_not_superseded_not_expired",
            "source_digest_current",
            "source_successful",
            "source_visible",
            "source_observed_by_subject",
            "membership_active",
            "not_blocked",
            "same_owner_world_subject_counterpart_thread",
        ],
        "executable_contract_gates": [
            "private_path_and_p5_preservation",
            "cjk_and_special_fts_syntax",
            "owner_world_subject_counterpart_thread_scope",
            "staging_promote_and_rollback",
            "stale_candidate_canonical_exclusion",
            "memory_off_zero_recall",
            "transaction_rollback_not_projected",
            "scope_off_and_delete_tombstone",
            "closed_typed_registry_and_hard_caps",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "retrieval_router_llm",
            "canonical_retrieval_planner_llm",
            "graph_retrieval_planner_llm",
            "ladybugdb_recall",
            "evidence_bundle_merge",
            "character_response_generator",
            "chat_send_stream_retry",
            "memory_owner_ui",
            "maintenance_llm_provider",
        ],
    }


def _check_frozen_successor_boundary() -> None:
    """Verify immutable P8-L-H evidence after I owns successor drift."""

    if _sha256(OUTPUT_PATH) != FROZEN_OUTPUT_SHA256:
        raise InventoryError("frozen P8-L-H inventory digest drift")
    inventory = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    predecessor = inventory.get("predecessor")
    if not isinstance(predecessor, dict):
        raise InventoryError("frozen P8-L-H predecessor is missing")
    predecessor_path = ROOT / str(predecessor.get("path") or "")
    if (
        not predecessor_path.is_file()
        or _sha256(predecessor_path) != predecessor.get("sha256")
    ):
        raise InventoryError("frozen P8-L-G predecessor digest drift")


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
                    "P8-L-H inventory is frozen; current-tree ownership moved to P8-L-I"
                )
            _check_frozen_successor_boundary()
            print("P8-L-H canonical recall inventory is frozen and chained to P8-L-I")
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
                "P8-L-H inventory drift; run python "
                "scripts/ci/generate_p8_l_h_memory_recall_inventory.py --write"
            )
        print("P8-L-H canonical recall inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-H inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
