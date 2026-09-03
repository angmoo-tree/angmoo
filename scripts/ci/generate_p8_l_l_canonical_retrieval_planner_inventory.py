"""Generate or verify the P8-L-L Canonical Retrieval Planner inventory."""

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

OUTPUT_PATH = (
    ROOT / "docs/architecture/p8-l-l-canonical-retrieval-planner-inventory.json"
)
K_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-k-retrieval-router-inventory.json"
K_INVENTORY_SHA256 = (
    "c10988bd12d35acb8a1a5607238001d1da551233f25c49a18785d224530aff9f"
)
CORPUS_PATH = (
    ROOT / "backend/tests/fixtures/p8_l/canonical_planner_v1/held_out_ko.jsonl"
)

from app.domains.chat.domain import RetrievalRoute  # noqa: E402
from app.domains.memory.public import (  # noqa: E402
    CANONICAL_PLAN_VERSION,
    CANONICAL_PRIMITIVE_REGISTRY,
    MAX_CANONICAL_PLAN_STEPS,
    canonical_retrieval_plan_response_schema,
)
from app.runtime.migrations.sqlite_versions.registry import (  # noqa: E402
    load_sqlite_manifest,
)
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402


class InventoryError(RuntimeError):
    """Stable failure for missing or drifting P8-L-L evidence."""


REQUIRED_FILES = (
    "backend/app/domains/memory/domain/canonical_retrieval_plan.py",
    "backend/app/domains/memory/domain/canonical_retrieval_planner.py",
    "backend/app/domains/memory/ports/canonical_planner_provider.py",
    "backend/app/domains/memory/application/canonical_planning.py",
    "backend/app/domains/chat/application/canonical_retrieval.py",
    "backend/app/domains/chat/domain/call_tracker.py",
    "backend/app/integrations/llm/canonical_retrieval_planner.py",
    "backend/tests/fixtures/p8_l/canonical_planner_v1/held_out_ko.jsonl",
    "backend/tests/test_p8_l_l_canonical_retrieval_planner.py",
    "backend/tests/test_p8_l_l_canonical_retrieval_planner_inventory.py",
    "docs/architecture/backend-domains.md",
    "docs/architecture/p8-l-l-canonical-retrieval-planner.md",
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
        operation.value for operation in CANONICAL_PRIMITIVE_REGISTRY
    }
    if len(rows) != 36 or len(case_ids) != len(set(case_ids)):
        raise InventoryError("P8-L-L held-out corpus cardinality drift")
    if set(operations) != expected_operations or set(operations.values()) != {4}:
        raise InventoryError("P8-L-L held-out operation coverage drift")
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
        "backend/app/domains/memory/domain/canonical_retrieval_planner.py",
        (
            "parse_canonical_retrieval_plan_payload",
            "canonical_retrieval_plan_response_schema",
            "canonical_plan_raw_query_forbidden",
            "canonical_plan_cross_axis_ref_forbidden",
            "source_refs",
        ),
    )
    _require_text(
        "backend/app/domains/memory/application/canonical_planning.py",
        (
            "CanonicalRetrievalPlanValidator",
            "CanonicalRetrievalPlanExecutor",
            "CanonicalRecallQuery",
            "canonical_dependency_empty",
            "context.row_limit",
        ),
    )
    _require_text(
        "backend/app/domains/chat/application/canonical_retrieval.py",
        (
            "CanonicalRetrievalPlanningService",
            "restore_call_tracker_snapshot",
            "canonical_planner_request_wide_repair_exhausted",
            "subject_world_character_id=resolved.responding_world_character_id",
        ),
    )
    _require_text(
        "backend/app/integrations/llm/canonical_retrieval_planner.py",
        (
            "DirectLlmCanonicalRetrievalPlannerProvider",
            "should_retry_json_error=lambda *_args: False",
            "character_id=None",
            "parse_canonical_retrieval_plan_payload",
        ),
    )
    return {
        "plan_owner": "domains/memory",
        "request_orchestration_owner": "domains/chat",
        "provider_port": "CanonicalPlannerProviderPort",
        "provider_adapter": "app.integrations.llm.canonical_retrieval_planner",
        "typed_executor": "CanonicalRetrievalPlanExecutor",
        "canonical_revalidation": "P8-L-H CanonicalRecallService",
        "provider_prompt_canonical_ids": 0,
        "provider_prompt_graph_catalog_entries": 0,
        "raw_sql_or_cypher_from_llm": 0,
        "test_live_provider_calls": 0,
        "existing_chat_send_path_changed": False,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(K_INVENTORY_PATH) != K_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-K predecessor digest drift")
    predecessor = json.loads(K_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-K":
        raise InventoryError("P8-L-K predecessor owner drift")
    if SQLITE_SCHEMA_VERSION < 6:
        raise InventoryError("P8-L-L must not change Embedded schema version")

    schema = canonical_retrieval_plan_response_schema()
    schema_text = json.dumps(schema, sort_keys=True).casefold()
    forbidden = [
        value
        for value in (
            "owner_id",
            "world_id",
            "thread_id",
            "character_id",
            "source_id",
            "event_id",
            "direct_relationship",
            "shortest_path",
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
        operation.value for operation in CANONICAL_PRIMITIVE_REGISTRY
    }
    if schema_operations != registry_operations:
        raise InventoryError("provider schema and H canonical registry drift")

    manifest = load_sqlite_manifest(6)
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-L",
        "contract_versions": {
            "canonical_plan": CANONICAL_PLAN_VERSION,
            "predecessor_resolved_retrieval": predecessor["contract_versions"][
                "resolved_retrieval"
            ],
        },
        "predecessor": _record(
            "docs/architecture/p8-l-k-retrieval-router-inventory.json"
        ),
        "historical_chain": {
            "p8_l_k_sha256": K_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-L",
        },
        "schema": {
            "new_alembic_migration": None,
            "new_embedded_schema_version": None,
            "current_embedded_schema_version": 6,
            "canonical_table_count": manifest.canonical_table_count,
            "new_canonical_tables": [],
            "new_ladybug_generation": None,
        },
        "domain_boundary": _boundary_contract(),
        "route": RetrievalRoute.CANONICAL.value,
        "provider_schema": {
            "version": CANONICAL_PLAN_VERSION,
            "max_steps": MAX_CANONICAL_PLAN_STEPS,
            "operation_count": len(schema_operations),
            "operations": sorted(schema_operations),
            "actual_id_fields": 0,
            "graph_operations": 0,
            "arbitrary_query_fields": 0,
            "dependency_slot": "prior_step.source_refs",
        },
        "code_owned_execution": {
            "owner_world_responding_subject_scope": True,
            "opaque_entity_to_actual_id_binding": True,
            "thread_binding": True,
            "absolute_utc_time_binding": True,
            "row_hard_cap": True,
            "memory_off_pre_provider_short_circuit": True,
            "dependency_zero_short_circuit": True,
            "fts_candidate_canonical_revalidation": True,
        },
        "call_accounting": {
            "canonical_normal_full_path_cap": 3,
            "normal_router_calls": 1,
            "normal_canonical_planner_calls": 1,
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
            "result_record_count",
            "provider",
            "model",
        ],
        "held_out_ko_contract": _corpus_contract(),
        "executable_contract_gates": [
            "canonical_only_exact_key_schema",
            "cross_catalog_and_actual_id_rejection",
            "raw_query_and_schema_material_rejection",
            "resolved_request_version_hash_binding",
            "opaque_entity_ref_resolution_by_code",
            "code_owned_scope_time_thread_and_row_cap",
            "typed_h_recall_and_canonical_revalidation",
            "prior_step_source_reference_dependency",
            "zero_dependency_short_circuit",
            "memory_off_pre_provider_short_circuit",
            "request_wide_single_repair_shared_with_router",
            "direct_adapter_no_hidden_json_retry",
            "held_out_ko_36_operation_complete_execution",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "graph_retrieval_planner_provider",
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
        rendered = json.dumps(
            inventory, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"
        if args.write:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()}")
            return 0
        if not OUTPUT_PATH.is_file():
            raise InventoryError("generated P8-L-L inventory is missing")
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-L inventory drift; run python "
                "scripts/ci/generate_p8_l_l_canonical_retrieval_planner_inventory.py --write"
            )
        print("P8-L-L Canonical Retrieval Planner inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-L inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
