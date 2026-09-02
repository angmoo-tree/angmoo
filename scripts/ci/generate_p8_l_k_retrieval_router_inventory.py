"""Generate or verify the P8-L-K Retrieval Router inventory."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-k-retrieval-router-inventory.json"
J_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-j-response-generation-inventory.json"
J_INVENTORY_SHA256 = (
    "e68f4ad4f2d1a1756c01d26b99c89fb145329036d431e680c1ece831f1fee4a5"
)
CORPUS_PATH = (
    ROOT / "backend/tests/fixtures/p8_l/retrieval_topology_v1/held_out_ko.jsonl"
)

from app.domains.chat.domain import (  # noqa: E402
    RESOLVED_RETRIEVAL_VERSION,
    RETRIEVAL_INTENT_VERSION,
    RetrievalHardCaps,
    RetrievalRoute,
    retrieval_router_response_schema,
)
from app.domains.chat.domain.retrieval_router import (  # noqa: E402
    ROUTER_AGGREGATION_TARGETS,
    ROUTER_CLARIFICATION_SLOTS,
    ROUTER_COORDINATION_HINTS,
    ROUTER_ENTITY_ROLES,
    ROUTER_INTENTS,
)
from app.domains.memory.public import CANONICAL_PRIMITIVE_REGISTRY  # noqa: E402
from app.domains.relationships.public import (  # noqa: E402
    GRAPH_RECALL_PRIMITIVE_REGISTRY,
)
from app.runtime.migrations.sqlite_versions.registry import (  # noqa: E402
    load_sqlite_manifest,
)
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402


class InventoryError(RuntimeError):
    """Stable failure for missing or drifting P8-L-K evidence."""


REQUIRED_FILES = (
    "backend/app/domains/chat/domain/retrieval_router.py",
    "backend/app/domains/chat/ports/retrieval_router_provider.py",
    "backend/app/domains/chat/ports/retrieval_policy.py",
    "backend/app/domains/chat/application/retrieval_routing.py",
    "backend/app/integrations/llm/retrieval_router.py",
    "backend/app/runtime/chat/retrieval_policy.py",
    "backend/tests/test_p8_l_k_retrieval_router.py",
    "backend/tests/test_oss_architecture_boundaries.py",
    "backend/tests/test_l4_pr_a_inventory.py",
    "docs/architecture/p8-l-k-retrieval-router.md",
    "security/l4_pr_a_inventory.json",
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
    routes = Counter(row["expected"]["route"] for row in rows)
    if len(rows) != 315 or len(case_ids) != len(set(case_ids)):
        raise InventoryError("P8-L-K held-out corpus cardinality drift")
    return {
        "schema_version": rows[0]["schema_version"],
        "case_count": len(rows),
        "unique_case_count": len(set(case_ids)),
        "category_counts": dict(sorted(categories.items())),
        "route_counts": dict(sorted(routes.items())),
        "live_model_evaluation_completed": False,
        "contract_normalization_executable": True,
    }


def _boundary_contract() -> dict[str, Any]:
    _require_text(
        "backend/app/domains/chat/domain/retrieval_router.py",
        (
            "parse_retrieval_intent_payload",
            "_require_exact_keys",
            "retrieval_router_forbidden_field",
            "retrieval_router_raw_query_forbidden",
            "retrieval_router_both_coordination_required",
        ),
    )
    _require_text(
        "backend/app/domains/chat/application/retrieval_routing.py",
        (
            "RetrievalRoutingService",
            "RetrievalRouterOutputError",
            "retrieval_router_request_wide_repair_exhausted",
            "ClarificationResolution",
            "ResolvedRetrievalEnvelope.bind_intent",
        ),
    )
    _require_text(
        "backend/app/integrations/llm/retrieval_router.py",
        (
            "DirectLlmRetrievalRouterProvider",
            "should_retry_json_error=lambda *_args: False",
            "character_id=None",
            "parse_retrieval_intent_payload",
        ),
    )
    _require_text(
        "backend/app/runtime/chat/retrieval_policy.py",
        (
            "SqlAlchemyRetrievalPolicyResolver",
            "LOCAL_INSTALLATION_KEY",
            "MessageThread.world_scope_status == \"resolved\"",
            "MemoryScopeSettingModel.enabled",
            "world_character_pair_is_blocked",
        ),
    )
    return {
        "backend_ownership": "domains/chat",
        "provider_port": "RetrievalRouterProviderPort",
        "provider_adapter": "app.integrations.llm.retrieval_router",
        "policy_port": "RetrievalPolicyResolverPort",
        "canonical_runtime_adapter": "app.runtime.chat.retrieval_policy",
        "provider_prompt_canonical_ids": 0,
        "provider_prompt_query_primitives": 0,
        "raw_sql_or_cypher_from_llm": 0,
        "test_live_provider_calls": 0,
        "existing_chat_send_path_changed": False,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(J_INVENTORY_PATH) != J_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-J predecessor digest drift")
    predecessor = json.loads(J_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-J":
        raise InventoryError("P8-L-J predecessor owner drift")
    if SQLITE_SCHEMA_VERSION != 6:
        raise InventoryError("P8-L-K must not change Embedded schema version")
    manifest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)
    schema = retrieval_router_response_schema()
    forbidden_schema_text = json.dumps(schema, sort_keys=True).casefold()
    forbidden = [
        value
        for value in ("owner_id", "world_id", "thread_id", "sql", "cypher")
        if value in forbidden_schema_text
    ]
    if forbidden:
        raise InventoryError(f"provider schema contains forbidden fields: {forbidden}")
    caps = RetrievalHardCaps()
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-K",
        "contract_versions": {
            "retrieval_intent": RETRIEVAL_INTENT_VERSION,
            "resolved_retrieval": RESOLVED_RETRIEVAL_VERSION,
        },
        "predecessor": _record(
            "docs/architecture/p8-l-j-response-generation-inventory.json"
        ),
        "historical_chain": {
            "p8_l_j_sha256": J_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-K",
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
        "routes": [route.value for route in RetrievalRoute],
        "semantic_catalogs": {
            "intents": sorted(ROUTER_INTENTS),
            "entity_roles": sorted(ROUTER_ENTITY_ROLES),
            "coordination_hints": sorted(ROUTER_COORDINATION_HINTS),
            "clarification_slots": sorted(ROUTER_CLARIFICATION_SLOTS),
            "aggregation_targets": sorted(ROUTER_AGGREGATION_TARGETS),
        },
        "code_owned_hard_caps": caps.payload(),
        "code_owned_operation_allowlists": {
            "canonical": sorted(
                operation.value for operation in CANONICAL_PRIMITIVE_REGISTRY
            ),
            "graph": sorted(
                operation.value for operation in GRAPH_RECALL_PRIMITIVE_REGISTRY
            ),
        },
        "clarification_policy": {
            "normal_route": True,
            "ambiguous_identity_direction_world_time_to_clarification": True,
            "ambiguity_broadened_to_both": False,
            "blocked_inactive_hidden_unobservable_candidates_exposed": 0,
            "retrieval_operations_on_clarification": 0,
        },
        "call_accounting": {
            "normal_router_logical_calls": 1,
            "request_wide_schema_repair_max": 1,
            "generic_hidden_json_repair": False,
            "logical_and_physical_separate": True,
            "current_context_full_path_cap": 2,
            "clarification_full_path_cap": 2,
        },
        "metrics": [
            "route",
            "first_pass_valid",
            "repair_used",
            "rejected",
            "clarification",
            "entity_resolution_outcome",
            "direction_resolution_outcome",
            "time_resolution_outcome",
            "router_logical_calls",
            "router_physical_attempts",
            "provider",
            "model",
        ],
        "held_out_ko_contract": _corpus_contract(),
        "executable_contract_gates": [
            "strict_exact_key_schema",
            "canonical_id_and_raw_query_rejection",
            "current_context_router_one_and_retrieval_zero",
            "same_world_entity_and_direction_binding",
            "world_timezone_to_absolute_utc",
            "immutable_intent_hash_binding",
            "route_specific_operation_allowlists",
            "ambiguity_to_safe_clarification_not_both",
            "blocked_candidate_non_disclosure",
            "request_wide_single_router_repair",
            "direct_adapter_no_hidden_json_retry",
            "held_out_ko_315_contract_normalization",
            "sqlalchemy_local_owner_world_thread_memory_scope",
            "runtime_boundary_uses_existing_relationship_block_port",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "canonical_retrieval_planner_provider",
            "graph_retrieval_planner_provider",
            "both_dependency_coordinator",
            "evidence_bundle",
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
            raise InventoryError("generated P8-L-K inventory is missing")
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-K inventory drift; run python "
                "scripts/ci/generate_p8_l_k_retrieval_router_inventory.py --write"
            )
        print("P8-L-K Retrieval Router inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-K inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
