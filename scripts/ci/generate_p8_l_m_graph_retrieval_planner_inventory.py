"""Generate or verify the P8-L-M Graph Retrieval Planner inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-m-graph-retrieval-planner-inventory.json"
L_INVENTORY_PATH = (
    ROOT / "docs/architecture/p8-l-l-canonical-retrieval-planner-inventory.json"
)
L_INVENTORY_SHA256 = (
    "1ae431d37dadb57ccb78502a9347df9059acd280ebf785aa91b5c3a581d8761c"
)
CORPUS_PATH = ROOT / "backend/tests/fixtures/p8_l/graph_planner_v1/held_out_ko.jsonl"

from app.domains.chat.domain import RetrievalRoute  # noqa: E402
from app.domains.relationships.public import (  # noqa: E402
    GRAPH_PLAN_VERSION,
    GRAPH_RECALL_PRIMITIVE_REGISTRY,
    MAX_GRAPH_PLAN_STEPS,
    graph_retrieval_plan_response_schema,
)
from app.runtime.migrations.sqlite_versions.registry import (  # noqa: E402
    load_sqlite_manifest,
)
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402


class InventoryError(RuntimeError):
    """Stable failure for missing or drifting P8-L-M evidence."""


REQUIRED_FILES = (
    "backend/app/domains/relationships/domain/graph_retrieval_plan.py",
    "backend/app/domains/relationships/domain/graph_retrieval_planner.py",
    "backend/app/domains/relationships/ports/graph_planner_provider.py",
    "backend/app/domains/relationships/application/graph_planning.py",
    "backend/app/domains/chat/application/graph_retrieval.py",
    "backend/app/domains/chat/domain/call_tracker.py",
    "backend/app/integrations/llm/graph_retrieval_planner.py",
    "backend/tests/fixtures/p8_l/graph_planner_v1/held_out_ko.jsonl",
    "backend/tests/test_p8_l_m_graph_retrieval_planner.py",
    "backend/tests/test_p8_l_m_graph_retrieval_planner_inventory.py",
    "docs/architecture/backend-domains.md",
    "docs/architecture/p8-l-m-graph-retrieval-planner.md",
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


def _corpus_contract() -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    case_ids = [row["case_id"] for row in rows]
    categories = Counter(row["category"] for row in rows)
    operations = Counter(row["expected"]["operation"] for row in rows)
    expected_operations = {
        operation.value for operation in GRAPH_RECALL_PRIMITIVE_REGISTRY
    }
    if len(rows) != 36 or len(case_ids) != len(set(case_ids)):
        raise InventoryError("P8-L-M held-out corpus cardinality drift")
    if set(operations) != expected_operations or set(operations.values()) != {6}:
        raise InventoryError("P8-L-M held-out operation coverage drift")
    return {
        "schema_version": rows[0]["schema_version"],
        "case_count": len(rows),
        "unique_case_count": len(set(case_ids)),
        "category_counts": dict(sorted(categories.items())),
        "operation_counts": dict(sorted(operations.items())),
        "live_model_evaluation_completed": False,
        "first_pass_contract_executable": True,
        "typed_execution_executable": True,
    }


def _boundary_contract() -> dict[str, Any]:
    _require_text(
        "backend/app/domains/relationships/domain/graph_retrieval_planner.py",
        (
            "parse_graph_retrieval_plan_payload",
            "graph_retrieval_plan_response_schema",
            "graph_plan_raw_query_forbidden",
            "graph_plan_cross_axis_ref_forbidden",
            "world_character_refs",
        ),
    )
    _require_text(
        "backend/app/domains/relationships/application/graph_planning.py",
        (
            "GraphRetrievalPlanValidator",
            "GraphRetrievalPlanExecutor",
            "GraphRecallQuery",
            "graph_dependency_empty",
            "context.max_hops",
            "context.fanout_limit",
        ),
    )
    _require_text(
        "backend/app/domains/chat/application/graph_retrieval.py",
        (
            "GraphRetrievalPlanningService",
            "restore_call_tracker_snapshot",
            "graph_planner_request_wide_repair_exhausted",
            "subject_world_character_id=resolved.responding_world_character_id",
        ),
    )
    _require_text(
        "backend/app/integrations/llm/graph_retrieval_planner.py",
        (
            "DirectLlmGraphRetrievalPlannerProvider",
            "should_retry_json_error=lambda *_args: False",
            "character_id=None",
            "parse_graph_retrieval_plan_payload",
        ),
    )
    return {
        "plan_owner": "domains/relationships",
        "request_orchestration_owner": "domains/chat",
        "provider_port": "GraphPlannerProviderPort",
        "provider_adapter": "app.integrations.llm.graph_retrieval_planner",
        "typed_executor": "GraphRetrievalPlanExecutor",
        "graph_query_boundary": "P8-L-I GraphRecallService",
        "canonical_revalidation": "P8-L-I SQLite facts and observation policy",
        "provider_prompt_canonical_ids": 0,
        "provider_prompt_canonical_catalog_entries": 0,
        "raw_sql_or_cypher_from_llm": 0,
        "test_live_provider_calls": 0,
        "existing_chat_send_path_changed": False,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(L_INVENTORY_PATH) != L_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-L predecessor digest drift")
    predecessor = json.loads(L_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-L":
        raise InventoryError("P8-L-L predecessor owner drift")
    if SQLITE_SCHEMA_VERSION != 6:
        raise InventoryError("P8-L-M must not change Embedded schema version")

    schema = graph_retrieval_plan_response_schema()
    schema_text = json.dumps(schema, sort_keys=True).casefold()
    forbidden = [
        value
        for value in (
            "owner_id",
            "world_id",
            "thread_id",
            "character_id",
            "relationship_state_id",
            "event_id",
            "search_thread_messages",
            "canonical_event_details",
            "sql",
            "cypher",
        )
        if value in schema_text
    ]
    if forbidden:
        raise InventoryError(f"provider schema contains forbidden fields: {forbidden}")
    schema_operations = set(
        schema["properties"]["steps"]["items"]["properties"]["operation"]["enum"]
    )
    registry_operations = {
        operation.value for operation in GRAPH_RECALL_PRIMITIVE_REGISTRY
    }
    if schema_operations != registry_operations:
        raise InventoryError("provider schema and I graph registry drift")

    manifest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-M",
        "contract_versions": {
            "graph_plan": GRAPH_PLAN_VERSION,
            "predecessor_canonical_plan": predecessor["contract_versions"][
                "canonical_plan"
            ],
        },
        "predecessor": _record(
            "docs/architecture/p8-l-l-canonical-retrieval-planner-inventory.json"
        ),
        "historical_chain": {
            "p8_l_l_sha256": L_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-M",
        },
        "schema": {
            "new_alembic_migration": None,
            "new_embedded_schema_version": None,
            "current_embedded_schema_version": SQLITE_SCHEMA_VERSION,
            "canonical_table_count": manifest.canonical_table_count,
            "new_canonical_tables": [],
            "new_ladybug_generation": None,
        },
        "domain_boundary": _boundary_contract(),
        "route": RetrievalRoute.GRAPH.value,
        "provider_schema": {
            "version": GRAPH_PLAN_VERSION,
            "max_steps": MAX_GRAPH_PLAN_STEPS,
            "operation_count": len(schema_operations),
            "operations": sorted(schema_operations),
            "actual_id_fields": 0,
            "canonical_operations": 0,
            "arbitrary_query_fields": 0,
            "dependency_slot": "prior_step.world_character_refs",
        },
        "code_owned_execution": {
            "owner_world_responding_subject_scope": True,
            "opaque_entity_to_actual_id_binding": True,
            "relationship_from_to_direction_binding": True,
            "row_hard_cap": True,
            "hop_hard_cap": True,
            "fanout_hard_cap": True,
            "unobservable_pre_provider_short_circuit": True,
            "dependency_zero_short_circuit": True,
            "ladybug_candidate_canonical_revalidation": True,
            "memory_off_does_not_disable_graph": True,
        },
        "call_accounting": {
            "graph_normal_full_path_cap": 3,
            "normal_router_calls": 1,
            "normal_graph_planner_calls": 1,
            "later_character_response_generator_calls": 1,
            "request_wide_schema_repair_max": 1,
            "generic_hidden_json_repair": False,
            "logical_and_physical_separate": True,
        },
        "metrics": [
            "first_pass_valid",
            "repair_used",
            "short_circuited",
            "short_circuit_reason",
            "planner_logical_calls",
            "planner_physical_attempts",
            "executable_step_count",
            "limit_clamped_step_count",
            "hop_clamped_step_count",
            "result_count",
            "provider",
            "model",
        ],
        "held_out_ko_contract": _corpus_contract(),
        "executable_contract_gates": [
            "graph_only_exact_key_schema",
            "cross_catalog_and_actual_id_rejection",
            "raw_query_cypher_and_schema_material_rejection",
            "resolved_request_version_hash_binding",
            "opaque_entity_ref_resolution_by_code",
            "code_owned_scope_direction_row_hop_and_fanout_caps",
            "typed_i_graph_recall_and_canonical_revalidation",
            "prior_step_world_character_reference_dependency",
            "zero_dependency_short_circuit",
            "unobservable_pre_provider_short_circuit",
            "memory_off_graph_independence",
            "request_wide_single_repair_shared_with_router",
            "direct_adapter_no_hidden_json_retry",
            "held_out_ko_36_operation_complete_execution",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "both_dependency_coordinator",
            "evidence_bundle_merge",
            "character_response_generator",
            "world_chat_send_retry_route_integration",
            "typing_presence_or_streaming_ui",
            "live_held_out_model_quality_pass",
            "installer_or_schema_change",
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
        rendered = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.write:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()}")
            return 0
        if not OUTPUT_PATH.is_file():
            raise InventoryError("generated P8-L-M inventory is missing")
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-M inventory drift; run python "
                "scripts/ci/generate_p8_l_m_graph_retrieval_planner_inventory.py --write"
            )
        print("P8-L-M Graph Retrieval Planner inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-M inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
