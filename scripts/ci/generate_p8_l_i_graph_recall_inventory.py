"""Generate or verify the P8-L-I graph recall facade inventory."""

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

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-i-graph-recall-inventory.json"
H_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-h-canonical-recall-inventory.json"
H_INVENTORY_SHA256 = (
    "1228178d70130040b453296c1ac71fcdd1b26b0347c0c7a0eb91d05d47e8ad48"
)

from app.domains.relationships.graph_recall import (  # noqa: E402
    GRAPH_RECALL_CONTRACT_VERSION,
    GRAPH_RECALL_PRIMITIVE_REGISTRY,
    MAX_GRAPH_RECALL_EDGES,
    MAX_GRAPH_RECALL_EVIDENCE,
    MAX_GRAPH_RECALL_HOPS,
    MAX_GRAPH_RECALL_RESULTS,
    GraphRecallOperation,
)


class InventoryError(RuntimeError):
    """Stable failure for missing or drifting P8-L-I evidence."""


REQUIRED_FILES = (
    "backend/app/domains/relationships/graph_recall/contracts.py",
    "backend/app/domains/relationships/graph_recall/service.py",
    "backend/app/domains/relationships/public.py",
    "backend/app/domains/relationships/graph_read/repository.py",
    "backend/app/runtime/graph_projection/relationship_graph_read.py",
    "backend/tests/test_p8_l_i_graph_recall.py",
    "docs/architecture/p8-l-i-graph-recall.md",
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
        "backend/app/domains/relationships/graph_recall/service.py",
        (
            "GRAPH_RECALL_PRIMITIVE_REGISTRY",
            "class GraphRecallValidator",
            "class GraphRecallService",
            "RelationshipGraphQueryPort",
            "graph_projection_lagging",
            "_canonical_shared_neighbor_ids",
            "_revalidate_evidence",
            "observed_by_subject",
        ),
    )
    _require_text(
        "backend/app/runtime/graph_projection/relationship_graph_read.py",
        (
            "def graph_recall_scope_access(",
            "def _subject_observed_event_ids(",
            "def execute_graph_recall(",
            "WorldCharacterFeedObservation",
            "invalidated_at.is_(None)",
            "blocked_with_subject",
        ),
    )
    _require_text(
        "backend/tests/test_p8_l_i_graph_recall.py",
        (
            "test_graph_recall_registry_is_closed_and_validator_enforces_hard_caps",
            "test_direct_and_evidence_replace_stale_projection_and_filter_unobserved",
            "test_shared_path_rank_and_neighborhood_are_canonically_revalidated",
            "test_graph_outage_has_bounded_fallback_without_raising",
            "test_runtime_facade_preserves_direction_evidence_and_owner_scope",
        ),
    )
    return {
        "backend_ownership": "domains/relationships",
        "public_facade": "app.domains.relationships.public",
        "runtime_composition": "app.runtime.graph_projection",
        "query_port": "RelationshipGraphQueryPort",
        "provider_dependency_in_domain": None,
        "planner_call_count": 0,
        "response_generator_call_count": 0,
        "raw_sql_or_cypher_from_llm": 0,
        "canonical_schema_changed": False,
        "ladybug_schema_changed": False,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(H_INVENTORY_PATH) != H_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-H predecessor digest drift")
    predecessor = json.loads(H_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-H":
        raise InventoryError("P8-L-H predecessor owner drift")
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-I",
        "contract_version": GRAPH_RECALL_CONTRACT_VERSION,
        "predecessor": _record(
            "docs/architecture/p8-l-h-canonical-recall-inventory.json"
        ),
        "historical_chain": {
            "p8_l_h_sha256": H_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-I",
        },
        "schema": {
            "new_alembic_migration": None,
            "new_embedded_schema_version": None,
            "new_canonical_tables": [],
            "new_ladybug_generation": None,
            "sqlite_remains_canonical": True,
            "ladybug_remains_replayable_projection": True,
        },
        "domain_boundary": _boundary_contract(),
        "typed_operations": [value.value for value in GraphRecallOperation],
        "primitive_registry": {
            operation.value: {
                "requires_counterpart": spec.requires_counterpart,
                "fallback_mode": spec.fallback_mode,
                "max_results": spec.max_results,
            }
            for operation, spec in GRAPH_RECALL_PRIMITIVE_REGISTRY.items()
        },
        "hard_caps": {
            "result_limit": MAX_GRAPH_RECALL_RESULTS,
            "evidence_limit": MAX_GRAPH_RECALL_EVIDENCE,
            "path_hops": MAX_GRAPH_RECALL_HOPS,
            "neighborhood_depth": 2,
            "neighborhood_edges": MAX_GRAPH_RECALL_EDGES,
        },
        "scope": [
            "owner_id",
            "world_id",
            "subject_world_character_id",
            "counterpart_world_character_id_when_required",
            "direction",
        ],
        "canonical_revalidation": [
            "same_world",
            "subject_owned_by_local_owner",
            "subject_and_candidate_membership_active",
            "not_deleted",
            "not_blocked",
            "relationship_direction_matches",
            "relationship_state_and_version_current",
            "source_event_succeeded_and_eligible",
            "source_event_not_invalidated",
            "source_visible_and_not_deleted_or_hidden",
            "source_observed_by_subject",
        ],
        "degraded_policy": {
            "direct_relationship": "bounded_canonical_exact_pair",
            "relationship_evidence": "bounded_canonical_pair_and_last_event",
            "shared_neighbors": "bounded_canonical_direct_set_intersection",
            "rank_related_characters": "bounded_canonical_subject_direct_ranking",
            "shortest_path": "no_evidence_no_relational_full_scan",
            "relationship_neighborhood": "no_evidence_no_relational_full_scan",
        },
        "executable_contract_gates": [
            "closed_registry_and_hard_caps",
            "direction_and_owner_world_scope",
            "stale_projection_replaced_by_canonical",
            "inactive_blocked_deleted_candidate_exclusion",
            "subject_observation_and_source_visibility",
            "shared_path_rank_neighborhood_revalidation",
            "graph_disabled_or_outage_bounded_fallback",
            "path_and_neighborhood_no_full_scan_degradation",
            "legacy_p7_graph_api_regression",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "retrieval_router_llm",
            "graph_retrieval_planner_llm",
            "canonical_retrieval_planner_llm",
            "retrieval_intent_or_resolved_envelope",
            "multi_step_graph_plan_schema",
            "both_dependency_coordinator",
            "evidence_bundle_merge",
            "character_response_generator",
            "chat_send_stream_retry",
            "memory_owner_ui",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        inventory = build_inventory()
        rendered = json.dumps(
            inventory,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        if args.write:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()}")
            return 0
        if not OUTPUT_PATH.is_file():
            raise InventoryError(
                "generated inventory is missing: "
                f"{OUTPUT_PATH.relative_to(ROOT).as_posix()}"
            )
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-I inventory drift; run python "
                "scripts/ci/generate_p8_l_i_graph_recall_inventory.py --write"
            )
        print("P8-L-I graph recall inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-I inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
