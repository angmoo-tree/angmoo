"""Generate or verify the P8-L-J response-generation lifecycle inventory."""

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

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-j-response-generation-inventory.json"
I_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-i-graph-recall-inventory.json"
I_INVENTORY_SHA256 = (
    "1de9f8218ddc8ecfb5af8a3a9873b0a84d71d6bf62f498a079d0f983f49569df"
)

from app.domains.chat.domain.call_tracker import (  # noqa: E402
    LlmNode,
    NORMAL_NODE_BUDGETS,
)
from app.domains.chat.domain.generation_lifecycle import (  # noqa: E402
    CHAT_GENERATION_STREAM_VERSION,
    ResponseRequestState,
    ResponseTerminalReason,
)
from app.domains.chat.domain.resolved_envelope import (  # noqa: E402
    RESOLVED_RETRIEVAL_VERSION,
)
from app.domains.chat.domain.retrieval_intent import (  # noqa: E402
    RETRIEVAL_INTENT_VERSION,
    RetrievalRoute,
)
from app.domains.chat.domain.workflow_recipe import (  # noqa: E402
    RETRIEVAL_WORKFLOW_VERSION,
    WorkflowRecipe,
)
from app.domains.chat.infrastructure.sqlalchemy_models import (  # noqa: E402
    ChatResponseRequest,
)
from app.domains.memory.domain.canonical_retrieval_plan import (  # noqa: E402
    CANONICAL_PLAN_VERSION,
    MAX_CANONICAL_PLAN_STEPS,
)
from app.domains.relationships.domain.graph_retrieval_plan import (  # noqa: E402
    GRAPH_PLAN_VERSION,
    MAX_GRAPH_PLAN_STEPS,
)
from app.runtime.migrations.sqlite_versions.registry import (  # noqa: E402
    load_sqlite_manifest,
)
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402


class InventoryError(RuntimeError):
    """Stable failure for missing or drifting P8-L-J evidence."""


REQUIRED_FILES = (
    "backend/app/domains/chat/domain/retrieval_intent.py",
    "backend/app/domains/chat/domain/resolved_envelope.py",
    "backend/app/domains/chat/domain/workflow_recipe.py",
    "backend/app/domains/chat/domain/call_tracker.py",
    "backend/app/domains/chat/domain/generation_lifecycle.py",
    "backend/app/domains/chat/domain/response_request.py",
    "backend/app/domains/chat/application/answer_request.py",
    "backend/app/domains/chat/application/generation_lifecycle.py",
    "backend/app/domains/chat/ports/response_lifecycle.py",
    "backend/app/domains/chat/infrastructure/response_lifecycle_repository.py",
    "backend/app/domains/memory/domain/canonical_retrieval_plan.py",
    "backend/app/domains/relationships/domain/graph_retrieval_plan.py",
    "backend/app/alembic/versions/20260831_0086_chat_response_request_lifecycle.py",
    "backend/app/runtime/migrations/sqlite_versions/v5_to_v6_chat_response_requests.py",
    "backend/app/runtime/migrations/sqlite_versions/manifests/v6.json",
    "backend/tests/test_p8_l_j_response_generation_lifecycle.py",
    "backend/tests/test_p8_l_j_response_generation_migration.py",
    "docs/architecture/p8-l-j-response-generation-lifecycle.md",
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
        "backend/app/domains/chat/application/answer_request.py",
        (
            "AnswerRequestContractValidator",
            "BoundedFakeAnswerRequestExecutor",
            "CANONICAL_PRIMITIVE_REGISTRY",
            "GRAPH_RECALL_PRIMITIVE_REGISTRY",
            "provider_calls: int = 0",
        ),
    )
    _require_text(
        "backend/app/domains/chat/infrastructure/response_lifecycle_repository.py",
        (
            "lease_generation=ChatResponseRequest.lease_generation + 1",
            "last_emitted_sequence",
            'logical.get("character_response_generator") != 1',
            "committed_assistant_message_id=assistant.id",
            "with self._session.begin_nested()",
        ),
    )
    _require_text(
        "backend/app/domains/chat/domain/call_tracker.py",
        (
            "llm_duplicate_crg_call",
            "llm_request_wide_repair_exceeded",
            "llm_physical_attempt_budget_exceeded",
        ),
    )
    _require_text(
        "backend/tests/test_p8_l_j_response_generation_lifecycle.py",
        (
            "test_fake_nodes_enforce_route_budget_without_live_provider",
            "test_request_wide_repair_and_duplicate_crg_are_fail_closed",
            "test_envelope_hash_cross_catalog_and_raw_query_are_rejected",
            "test_renewed_lease_rejects_old_fence_and_sequence_gap",
            "test_fenced_finalize_is_atomic_idempotent_and_stores_no_partial_delta",
            "test_deadline_prevents_late_transition_and_physical_retry_is_visible",
        ),
    )
    return {
        "backend_ownership": "domains/chat",
        "canonical_plan_ownership": "domains/memory",
        "graph_plan_ownership": "domains/relationships",
        "public_facade": "app.domains.chat.public",
        "runtime_composition": "app.runtime.chat",
        "live_router_provider_calls": 0,
        "live_canonical_planner_provider_calls": 0,
        "live_graph_planner_provider_calls": 0,
        "live_character_response_generator_calls": 0,
        "fake_executor_provider_calls": 0,
        "raw_sql_or_cypher_from_llm": 0,
        "existing_chat_provider_path_changed": False,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(I_INVENTORY_PATH) != I_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-I predecessor digest drift")
    predecessor = json.loads(I_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-I":
        raise InventoryError("P8-L-I predecessor owner drift")

    manifest = load_sqlite_manifest(6)
    if SQLITE_SCHEMA_VERSION < 6 or manifest.canonical_table_count != 95:
        raise InventoryError("P8-L-J embedded schema contract drift")
    columns = [column.name for column in ChatResponseRequest.__table__.columns]
    forbidden_columns = {
        "raw_delta",
        "partial_response",
        "typing_presence",
        "socket_state",
        "provider_response_body",
        "reasoning",
    }
    if forbidden_columns.intersection(columns):
        raise InventoryError("response request stores forbidden transient payload")

    route_budgets = {
        route.value: {
            "nodes": {
                node.value: NORMAL_NODE_BUDGETS[route][node] for node in LlmNode
            },
            "normal_full_path": sum(NORMAL_NODE_BUDGETS[route].values()),
            "request_wide_repair_max": 1,
        }
        for route in RetrievalRoute
    }
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-J",
        "contract_versions": {
            "retrieval_intent": RETRIEVAL_INTENT_VERSION,
            "resolved_retrieval": RESOLVED_RETRIEVAL_VERSION,
            "canonical_plan": CANONICAL_PLAN_VERSION,
            "graph_plan": GRAPH_PLAN_VERSION,
            "workflow": RETRIEVAL_WORKFLOW_VERSION,
            "generation_stream": CHAT_GENERATION_STREAM_VERSION,
        },
        "predecessor": _record(
            "docs/architecture/p8-l-i-graph-recall-inventory.json"
        ),
        "historical_chain": {
            "p8_l_i_sha256": I_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-J",
        },
        "schema": {
            "new_alembic_migration": "20260831_0086",
            "new_embedded_schema_version": 6,
            "new_canonical_tables": ["chat_response_requests"],
            "canonical_table_count": manifest.canonical_table_count,
            "source_revision": manifest.source_revision,
            "source_migration_count": manifest.source_migration_count,
            "new_ladybug_generation": None,
            "sqlite_remains_canonical": True,
            "ladybug_remains_replayable_projection": True,
        },
        "domain_boundary": _boundary_contract(),
        "plan_limits": {
            "canonical_steps": MAX_CANONICAL_PLAN_STEPS,
            "graph_steps": MAX_GRAPH_PLAN_STEPS,
            "workflow_recipes": [recipe.value for recipe in WorkflowRecipe],
        },
        "route_call_budgets": route_budgets,
        "call_accounting": {
            "logical_and_physical_separate": True,
            "physical_attempts_per_logical_max": 2,
            "character_response_generator_logical_max": 1,
            "character_response_generator_repair_allowed": False,
            "request_wide_schema_repair_max": 1,
            "deadline_and_cancel_enforced": True,
        },
        "lifecycle": {
            "states": [state.value for state in ResponseRequestState],
            "terminal_reasons": [reason.value for reason in ResponseTerminalReason],
            "renewable_lease_generation": True,
            "fenced_compare_and_swap": True,
            "monotonic_stream_sequence": True,
            "duplicate_sequence_idempotent": True,
            "gap_or_reversal_rejected": True,
            "late_result_rejected": True,
            "assistant_and_metadata_and_commit_atomic": True,
            "duplicate_assistant_commit_max": 0,
        },
        "canonical_response_request": {
            "table": "chat_response_requests",
            "columns": columns,
            "raw_partial_delta_columns": 0,
            "memory_candidate_before_committed_ok": 0,
        },
        "installer_upgrade_matrix": {
            "readable_predecessors": [1, 2, 3, 4, 5],
            "target_version": 6,
            "v5_retains_memory_schema": True,
            "v5_omits_response_request_schema": True,
        },
        "executable_contract_gates": [
            "route_budget_matrix_and_zero_provider_calls",
            "request_wide_single_repair",
            "single_character_response_generator",
            "intent_resolved_plan_hash_binding",
            "closed_h_i_primitive_catalogs",
            "no_raw_sql_or_cypher",
            "renewable_lease_stale_fence_rejection",
            "monotonic_stream_sequence",
            "deadline_cancel_and_late_result_rejection",
            "atomic_fenced_assistant_commit",
            "duplicate_finalize_idempotency",
            "no_transient_delta_canonical_storage",
            "v5_to_v6_copy_on_write_preservation",
            "v1_to_v5_real_installer_predecessor_matrix",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "live_retrieval_router_provider_adapter",
            "live_canonical_retrieval_planner_provider_adapter",
            "live_graph_retrieval_planner_provider_adapter",
            "live_character_response_generator_provider_adapter",
            "new_world_chat_send_or_retry_api",
            "sse_or_websocket_stream_transport",
            "typing_presence_and_retry_ui",
            "evidence_bundle_content_policy",
            "assistant_message_memory_candidate_creation",
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
        # Today SNS owns current-tree contracts; preserve the exact predecessor
        # inventory rather than rewriting historical evidence for schema v8.
        if (ROOT / "docs/architecture/p8-l-r-today-sns-activity-inventory.json").is_file():
            if _sha256(OUTPUT_PATH) != "fd039b7f4db5c4ad300b28cc031e1789a79a185ebee67ed23fb16187b5f160da":
                raise InventoryError("frozen predecessor inventory digest drift")
            print("Historical inventory is frozen by the Today SNS successor")
            return 0
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
                "P8-L-J inventory drift; run python "
                "scripts/ci/generate_p8_l_j_response_generation_inventory.py --write"
            )
        print("P8-L-J response-generation inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-J inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
