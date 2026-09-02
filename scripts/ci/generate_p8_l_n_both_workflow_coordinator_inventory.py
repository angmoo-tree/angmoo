"""Generate or verify the P8-L-N BOTH Workflow Coordinator inventory."""

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

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-n-both-workflow-coordinator-inventory.json"
M_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-m-graph-retrieval-planner-inventory.json"
M_INVENTORY_SHA256 = (
    "ef4ebadee0507c05dba672c316b5dd139084e6eb9743325d4e02f24699ae5d46"
)

from app.domains.chat.domain import (  # noqa: E402
    RETRIEVAL_WORKFLOW_VERSION,
    WORKFLOW_RECIPE_REGISTRY,
    WorkflowAxis,
    WorkflowDependencyKind,
    WorkflowMergeMode,
    WorkflowRecipe,
)
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402


class InventoryError(RuntimeError):
    pass


REQUIRED_FILES = (
    "backend/app/domains/chat/application/__init__.py",
    "backend/app/domains/chat/application/both_retrieval.py",
    "backend/app/domains/chat/application/canonical_retrieval.py",
    "backend/app/domains/chat/application/graph_retrieval.py",
    "backend/app/domains/chat/domain/__init__.py",
    "backend/app/domains/chat/domain/call_tracker.py",
    "backend/app/domains/chat/domain/workflow_recipe.py",
    "backend/app/domains/chat/public.py",
    "backend/tests/test_p8_l_n_both_workflow_coordinator.py",
    "backend/tests/test_p8_l_n_both_workflow_coordinator_inventory.py",
    "docs/architecture/backend-domains.md",
    "docs/architecture/p8-l-n-both-workflow-coordinator.md",
    "scripts/ci/generate_p8_l_n_both_workflow_coordinator_inventory.py",
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


def _forbid_imports(relative: str, prefixes: tuple[str, ...]) -> None:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    forbidden = [
        module
        for module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)
    ]
    if forbidden:
        raise InventoryError(f"{relative}: forbidden imports: {forbidden}")


def _recipe_contract() -> dict[str, Any]:
    expected = {
        WorkflowRecipe.INDEPENDENT_PARALLEL: {
            "axes": [WorkflowAxis.CANONICAL.value, WorkflowAxis.GRAPH.value],
            "parallel": True,
            "dependency": None,
            "merge": WorkflowMergeMode.UNION.value,
            "intents": ["mixed_evidence", "relationship_comparison"],
        },
        WorkflowRecipe.GRAPH_THEN_CANONICAL: {
            "axes": [WorkflowAxis.GRAPH.value, WorkflowAxis.CANONICAL.value],
            "parallel": False,
            "dependency": WorkflowDependencyKind.EVENT_REFERENCES.value,
            "merge": WorkflowMergeMode.INTERSECTION.value,
            "intents": [
                "relationship_cause",
                "relationship_path",
                "relationship_state",
            ],
        },
        WorkflowRecipe.CANONICAL_THEN_GRAPH: {
            "axes": [WorkflowAxis.CANONICAL.value, WorkflowAxis.GRAPH.value],
            "parallel": False,
            "dependency": WorkflowDependencyKind.WORLD_CHARACTER_REFERENCES.value,
            "merge": WorkflowMergeMode.INTERSECTION.value,
            "intents": ["event_aggregation", "historical_recall"],
        },
    }
    if set(WORKFLOW_RECIPE_REGISTRY) != set(expected):
        raise InventoryError("P8-L-N recipe registry keys drift")
    rendered: dict[str, Any] = {}
    for recipe, wanted in expected.items():
        spec = WORKFLOW_RECIPE_REGISTRY[recipe]
        actual = {
            "axes": [axis.value for axis in spec.planner_axes],
            "parallel": spec.planners_parallel,
            "dependency": (
                None if spec.dependency_kind is None else spec.dependency_kind.value
            ),
            "merge": spec.merge_mode.value,
            "intents": sorted(spec.intents),
        }
        if actual != wanted or spec.normal_planner_call_cap != 2:
            raise InventoryError(f"P8-L-N recipe drift: {recipe.value}")
        rendered[recipe.value] = {
            **actual,
            "normal_planner_call_cap": spec.normal_planner_call_cap,
        }
    return rendered


def _boundary_contract() -> dict[str, Any]:
    _require_text(
        "backend/app/domains/chat/domain/workflow_recipe.py",
        (
            "WORKFLOW_RECIPE_REGISTRY",
            "select_workflow_recipe",
            "WorkflowDependencyBinding",
            "graph-result.event_refs",
            "canonical-result.world_character_refs",
            "normal_planner_call_cap: int = 2",
        ),
    )
    _require_text(
        "backend/app/domains/chat/application/both_retrieval.py",
        (
            "BothRetrievalWorkflowCoordinator",
            "asyncio.gather",
            "restore_call_tracker_snapshot",
            "workflow_dependency_empty",
            "_intersection_groups",
            "_deduplicate_groups",
            "coordinator_llm_calls: int = 0",
        ),
    )
    _require_text(
        "backend/app/domains/chat/application/canonical_retrieval.py",
        ("allow_both=coordinator_owned", "workflow_dependency"),
    )
    _require_text(
        "backend/app/domains/chat/application/graph_retrieval.py",
        ("allow_both=coordinator_owned", "workflow_dependency"),
    )
    _forbid_imports(
        "backend/app/domains/chat/application/both_retrieval.py",
        (
            "app.integrations",
            "app.runtime",
            "app.infrastructure",
            "sqlalchemy",
            "fastapi",
        ),
    )
    return {
        "owner": "app.domains.chat",
        "canonical_boundary": "app.domains.memory.public",
        "graph_boundary": "app.domains.relationships.public",
        "provider_adapter": None,
        "coordinator_llm_nodes": 0,
        "raw_sql_or_cypher": 0,
        "arbitrary_workflow_expressions": 0,
        "runtime_or_persistence_imports": 0,
        "specialist_provider_actual_dependency_values": 0,
        "test_live_provider_calls": 0,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(M_INVENTORY_PATH) != M_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-M predecessor digest drift")
    predecessor = json.loads(M_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-M":
        raise InventoryError("P8-L-M predecessor owner drift")
    if SQLITE_SCHEMA_VERSION != 6:
        raise InventoryError("P8-L-N must not change Embedded schema version")

    return {
        "schema_version": 1,
        "owner_stage": "P8-L-N",
        "contract_versions": {
            "workflow": RETRIEVAL_WORKFLOW_VERSION,
            "predecessor_graph_plan": predecessor["contract_versions"]["graph_plan"],
            "predecessor_canonical_plan": predecessor["contract_versions"][
                "predecessor_canonical_plan"
            ],
        },
        "predecessor": _record(
            "docs/architecture/p8-l-m-graph-retrieval-planner-inventory.json"
        ),
        "historical_chain": {
            "p8_l_m_sha256": M_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-N",
        },
        "schema": {
            "new_alembic_migration": None,
            "new_embedded_schema_version": None,
            "current_embedded_schema_version": SQLITE_SCHEMA_VERSION,
            "new_canonical_tables": [],
            "new_ladybug_generation": None,
        },
        "domain_boundary": _boundary_contract(),
        "recipe_registry": _recipe_contract(),
        "dependency_contract": {
            "opaque_slots": [
                "canonical-result.world_character_refs",
                "graph-result.event_refs",
            ],
            "actual_values_bound_by_code": True,
            "fanout_hard_cap": True,
            "zero_dependency_downstream_planner_short_circuit": True,
            "policy_denial_downstream_planner_short_circuit": True,
            "cycles": 0,
            "unbounded_fanout": 0,
            "result_driven_replanning": 0,
        },
        "deterministic_merge": {
            "event_reference_join": True,
            "world_character_reference_join": True,
            "dependent_intersection": True,
            "independent_union": True,
            "dedupe": True,
            "stable_ranking": True,
            "resolved_row_cap": True,
            "evidence_bundle_created": False,
        },
        "call_accounting": {
            "both_normal_full_path_cap": 4,
            "normal_router_calls": 1,
            "normal_canonical_planner_calls": 1,
            "normal_graph_planner_calls": 1,
            "later_character_response_generator_calls": 1,
            "coordinator_llm_calls": 0,
            "request_wide_schema_repair_max": 1,
            "shared_tracker_for_parallel_planners": True,
        },
        "executable_contract_gates": [
            "intent_typed_code_recipe_selection",
            "incompatible_router_hint_code_override",
            "independent_specialist_planner_parallel_start",
            "graph_then_canonical_event_dependency",
            "canonical_then_graph_world_character_dependency",
            "opaque_dependency_actual_value_code_binding",
            "zero_dependency_and_policy_downstream_short_circuit",
            "deterministic_join_intersection_rank_and_dedupe",
            "shared_request_wide_single_repair",
            "both_full_path_cap_four_with_crg_reserved",
            "coordinator_llm_zero",
            "specialist_standalone_both_rejection",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "evidence_bundle_snapshot",
            "character_response_generator",
            "assistant_message_commit",
            "world_chat_send_retry_route_integration",
            "typing_presence_or_streaming_ui",
            "live_model_quality_or_latency_pass",
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
            raise InventoryError("generated P8-L-N inventory is missing")
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-N inventory drift; run python "
                "scripts/ci/generate_p8_l_n_both_workflow_coordinator_inventory.py --write"
            )
        print("P8-L-N BOTH Workflow Coordinator inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-N inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
