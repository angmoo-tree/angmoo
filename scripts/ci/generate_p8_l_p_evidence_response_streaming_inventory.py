"""Generate or verify the P8-L-P response-streaming inventory."""

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

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-p-evidence-response-streaming-inventory.json"
O_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-o-memory-consolidation-inventory.json"
O_INVENTORY_SHA256 = "3a9341c11a12d1c33e4007a3eb641afdd28b0f22545d6ff09d3dd908a6120aed"

from app.domains.chat.domain import CHAT_GENERATION_STREAM_VERSION  # noqa: E402
from app.domains.chat.domain.evidence_bundle import (  # noqa: E402
    EVIDENCE_BUNDLE_VERSION,
    MAX_EVIDENCE_BUNDLE_CHARS,
    MAX_EVIDENCE_ITEM_CHARS,
    MAX_EVIDENCE_ITEMS,
)
from app.domains.chat.domain.retrieval_router import (  # noqa: E402
    ROUTER_DIAGNOSTIC_VERSION,
    ROUTER_SECURITY_VALIDATION_CODES,
    ROUTER_VALIDATION_CODES,
    retrieval_router_response_schema,
)
from app.integrations.llm.character_response_generator import (  # noqa: E402
    CHARACTER_RESPONSE_MAX_OUTPUT_TOKENS,
    CHARACTER_RESPONSE_TIMEOUT_SECONDS,
)
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest  # noqa: E402
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402


class InventoryError(RuntimeError):
    pass


REQUIRED_FILES = (
    "backend/app/alembic/versions/20260903_0087_world_chat_model_binding.py",
    "backend/app/api/v1/routes/world_chat.py",
    "backend/app/api/v1/routes/world_chat_response.py",
    "backend/app/domains/chat/api/schemas.py",
    "backend/app/domains/chat/application/character_response.py",
    "backend/app/domains/chat/application/evidence_assembly.py",
    "backend/app/domains/chat/application/generation_lifecycle.py",
    "backend/app/domains/chat/application/retrieval_routing.py",
    "backend/app/domains/chat/application/response_workflow.py",
    "backend/app/domains/chat/domain/evidence_bundle.py",
    "backend/app/domains/chat/domain/model_binding.py",
    "backend/app/domains/chat/domain/retrieval_router.py",
    "backend/app/domains/chat/infrastructure/model_binding_migration.py",
    "backend/app/domains/chat/infrastructure/response_lifecycle_repository.py",
    "backend/app/domains/chat/infrastructure/sqlalchemy_models.py",
    "backend/app/domains/chat/ports/character_response_generator.py",
    "backend/app/domains/chat/ports/response_lifecycle.py",
    "backend/app/domains/chat/ports/retrieval_router_provider.py",
    "backend/app/domains/chat/ports/response_workflow.py",
    "backend/app/domains/chat/ports/successful_chat_memory.py",
    "backend/app/integrations/direct_llm.py",
    "backend/app/integrations/llm/retrieval_router.py",
    "backend/app/integrations/llm/character_response_generator.py",
    "backend/app/providers/gemini.py",
    "backend/app/runtime/chat/memory_producer.py",
    "backend/app/runtime/chat/sqlalchemy_service.py",
    "backend/app/runtime/chat/world_generation.py",
    "backend/app/runtime/migrations/sqlite_versions/registry.py",
    "backend/app/runtime/migrations/sqlite_versions/v6_to_v7_chat_model_binding.py",
    "backend/app/runtime/migrations/sqlite_versions/manifests/v7.json",
    "backend/app/runtime/persistence/sqlite_schema.py",
    "backend/app/runtime/memory/sqlalchemy_source_reader.py",
    "backend/tests/test_p8_l_p_evidence_response_streaming.py",
    "backend/tests/test_p8_l_p_frontend_streaming.py",
    "backend/tests/test_p8_l_p_model_hotfix.py",
    "backend/tests/test_p8_l_k_retrieval_router.py",
    "backend/tests/fixtures/p8_l/router_hotfix_v1/current_context_ko.jsonl",
    "browser-tests/product-shell.spec.ts",
    "browser-tests/static-product-shell.spec.ts",
    "frontend/DESIGN.md",
    "frontend/src/features/chat/api/world-chat-client.ts",
    "frontend/src/features/chat/model/world-chat-contract.ts",
    "frontend/src/features/chat/ui/world-chat.module.css",
    "frontend/src/features/chat/ui/world-chat.tsx",
    "docs/architecture/backend-domains.md",
    "docs/architecture/frontend-design-reference.md",
    "docs/architecture/frontend-product-shell.md",
    "docs/architecture/p8-l-p-evidence-response-streaming.md",
    "scripts/ci/build_windows_installer_supported_upgrade_fixture.py",
    "scripts/ci/generate_p8_l_p_evidence_response_streaming_inventory.py",
    "scripts/ci/verify_windows_installer_supported_upgrade_fixture.py",
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
        "backend/app/domains/chat/domain/evidence_bundle.py",
        "backend/app/domains/chat/application/character_response.py",
        "backend/app/domains/chat/application/evidence_assembly.py",
        "backend/app/domains/chat/application/response_workflow.py",
        "backend/app/domains/chat/ports/character_response_generator.py",
        "backend/app/domains/chat/ports/successful_chat_memory.py",
    ):
        _forbid_imports(
            relative,
            ("app.integrations", "app.runtime", "sqlalchemy", "fastapi"),
        )
    _require_text(
        "backend/app/domains/chat/application/response_workflow.py",
        (
            "ResponseRequestState.EVIDENCE_FROZEN",
            "CharacterResponseGeneratorRequest",
            'payload={"text": delta}',
            "self._unit_of_work.checkpoint()",
            "self._propose_memory_after_commit(command, committed)",
        ),
    )
    _require_text(
        "backend/app/runtime/chat/memory_producer.py",
        (
            "MemorySourceTypeV1.CHAT_MESSAGE",
            "MemoryKindV1.AUTOBIOGRAPHICAL_EVENT",
            "self._session.commit()",
            "self._session.rollback()",
        ),
    )
    _require_text(
        "frontend/src/features/chat/ui/world-chat.tsx",
        (
            "}, 300);",
            "입력 중",
            "다시 보내기",
            "다시 시도 중",
            "답장을 만들지 못했어요.",
            "기본 모델 사용",
            "모델을 바꾸지 못했어요.",
            "data-response-slot",
        ),
    )
    _require_text(
        "frontend/src/features/chat/api/world-chat-client.ts",
        (
            'Accept: "application/x-ndjson"',
            "world_chat_stream_sequence_gap",
            "world_chat_stream_payload_invalid",
        ),
    )
    _require_text(
        "backend/app/providers/gemini.py",
        ("thinkingLevel", "thinkingBudget", "Gemma"),
    )
    _require_text(
        "backend/app/domains/chat/application/response_workflow.py",
        (
            "failure_diagnostic",
            "_provider_failure_diagnostic",
            "router_diagnostic",
            "_router_failure_diagnostic",
            "router_schema_rejected",
        ),
    )
    _require_text(
        "backend/app/domains/chat/domain/retrieval_router.py",
        (
            "RouterFailureDiagnostic",
            "ROUTER_VALIDATION_CODES",
            "ROUTER_SECURITY_VALIDATION_CODES",
            '"required": ["kind", "expression"]',
        ),
    )
    router_schema = retrieval_router_response_schema()
    router_schema_text = json.dumps(router_schema, sort_keys=True).casefold()
    if "additionalproperties" in router_schema_text:
        raise InventoryError("Router provider schema uses unsupported additionalProperties")
    if set(router_schema["required"]) != set(router_schema["properties"]):
        raise InventoryError("Router provider schema top-level required fields drift")
    _require_text(
        "backend/app/integrations/llm/retrieval_router.py",
        (
            "router_validation_code_from_exception",
            '"validation_code": request.repair_diagnostic',
            "안녕 지금 기분이 어때?",
        ),
    )
    _require_text(
        "backend/app/domains/chat/infrastructure/model_binding_migration.py",
        ("model_binding_mode", "validate_resolved_default_models"),
    )
    return {
        "chat_owner": "app.domains.chat",
        "memory_owner": "app.domains.memory",
        "provider_adapter": "app.integrations.llm.character_response_generator",
        "runtime_composition": "app.runtime.chat.world_generation",
        "frontend_feature": "frontend/src/features/chat",
        "domain_application_framework_imports": 0,
        "raw_sql_or_cypher_from_llm": 0,
        "router_planner_or_database_public_deltas": 0,
        "assistant_commit_owner": "code",
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(O_INVENTORY_PATH) != O_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-O predecessor digest drift")
    predecessor = json.loads(O_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-O":
        raise InventoryError("P8-L-O predecessor owner drift")
    if SQLITE_SCHEMA_VERSION != 7:
        raise InventoryError("P8-L-P Hotfix must own Embedded schema v7")
    manifest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)

    return {
        "schema_version": 1,
        "owner_stage": "P8-L-P",
        "contract_versions": {
            "stream": CHAT_GENERATION_STREAM_VERSION,
            "evidence_bundle": EVIDENCE_BUNDLE_VERSION,
        },
        "predecessor": _record(
            "docs/architecture/p8-l-o-memory-consolidation-inventory.json"
        ),
        "historical_chain": {
            "p8_l_o_sha256": O_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-P",
        },
        "schema": {
            "new_alembic_migration": "20260903_0087",
            "new_embedded_schema_version": 7,
            "current_embedded_schema_version": SQLITE_SCHEMA_VERSION,
            "new_canonical_tables": [],
            "new_canonical_columns": ["message_threads.model_binding_mode"],
            "canonical_table_count": manifest.canonical_table_count,
            "source_revision": manifest.source_revision,
            "source_migration_count": manifest.source_migration_count,
            "new_ladybug_generation": None,
        },
        "domain_boundary": _boundary_contract(),
        "bounds": {
            "evidence_items": MAX_EVIDENCE_ITEMS,
            "evidence_item_characters": MAX_EVIDENCE_ITEM_CHARS,
            "evidence_bundle_characters": MAX_EVIDENCE_BUNDLE_CHARS,
            "character_response_output_tokens": CHARACTER_RESPONSE_MAX_OUTPUT_TOKENS,
            "character_response_timeout_seconds": CHARACTER_RESPONSE_TIMEOUT_SECONDS,
            "character_response_logical_calls_per_attempt": 1,
            "request_wide_schema_repairs": 1,
            "visible_typing_delay_milliseconds": 300,
            "visible_typing_instances_per_generation": 1,
        },
        "route_call_caps": {
            "CURRENT_CONTEXT": 2,
            "CANONICAL": 3,
            "GRAPH": 3,
            "BOTH": 4,
            "CLARIFICATION": 2,
        },
        "stream_contract": {
            "transport": "application/x-ndjson",
            "public_event_types": [
                "accepted",
                "delta",
                "completed",
                "failed",
                "cancelled",
            ],
            "delta_payload_keys": ["text"],
            "provider_native_token_stream_claimed": False,
            "verified_crg_text_chunked_after_generation": True,
            "monotonic_sequence": True,
            "scope_generation_attempt_fence": True,
            "terminal_canonical_rehydrate": True,
        },
        "memory_after_commit": {
            "source_type": "CHAT_MESSAGE",
            "memory_kind": "AUTOBIOGRAPHICAL_EVENT",
            "source": "committed_assistant_message",
            "default_off_writes": 0,
            "failed_or_partial_writes": 0,
            "idempotent_candidate_per_source": True,
            "producer_failure_rolls_back_chat": False,
        },
        "model_hotfix": {
            "binding_modes": ["default", "thread_override"],
            "accepted_request_model_snapshot_immutable": True,
            "active_generation_model_update_status": 409,
            "default_binding_follows_current_product_preference": True,
            "explicit_retry_resnapshots_current_binding": True,
            "gemini_3_thinking_field": "thinkingLevel",
            "gemini_2_5_low_thinking_budget": 0,
            "gemma_thinking_config": None,
            "unknown_model_family": "fail_before_provider_io",
            "durable_provider_diagnostic_fields": [
                "node",
                "provider",
                "model",
                "failure_class",
                "provider_status",
                "provider_code",
                "provider_error_hint",
                "retryable",
            ],
            "world_scoped_selector": True,
            "model_update_failure_rolls_back": True,
        },
        "router_hotfix": {
            "diagnostic_version": ROUTER_DIAGNOSTIC_VERSION,
            "durable_namespace": "node_state_json.router_diagnostic",
            "validation_codes": sorted(ROUTER_VALIDATION_CODES),
            "security_nonretryable_codes": sorted(
                ROUTER_SECURITY_VALIDATION_CODES
            ),
            "raw_router_payload_persisted": False,
            "repair_validation_code_only": True,
            "current_mood_fixture_count": 3,
            "safe_mismatch_explicit_retry": True,
            "automatic_retry": False,
            "failed_before_route_crg_calls": 0,
            "new_schema_migration": None,
        },
        "executable_contract_gates": [
            "all_five_routes_call_caps_and_single_crg",
            "deterministic_bounded_provider_safe_evidence",
            "crg_only_public_delta",
            "fenced_atomic_assistant_commit",
            "terminal_replay_without_regeneration",
            "typed_retryable_failure_rehydrate",
            "send_idempotency_and_retry_stable_slot",
            "partial_assistant_and_memory_candidate_zero",
            "successful_chat_after_commit_candidate",
            "memory_off_and_producer_failure_isolation",
            "typing_delay_and_first_delta_replacement",
            "stale_scope_generation_attempt_sequence_guard",
            "default_and_override_model_binding",
            "accepted_request_model_snapshot_and_retry_resnapshot",
            "provider_family_thinking_compatibility",
            "safe_durable_provider_failure_diagnostic",
            "embedded_v6_to_v7_model_binding_upgrade",
            "model_selector_busy_guard_and_failure_rollback",
            "router_nested_schema_parser_parity",
            "router_safe_durable_diagnostic",
            "current_mood_minimal_current_context",
            "router_safe_mismatch_explicit_retry",
            "router_security_rejection_nonretryable",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "memory_read_or_owner_control_ui",
            "provider_native_token_transport",
            "held_out_quality_or_latency_pass",
            "cross_runtime_user_gate",
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
        inventory = build_inventory()
        rendered = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.write:
            OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()}")
            return 0
        if not OUTPUT_PATH.is_file():
            raise InventoryError("generated P8-L-P inventory is missing")
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-P inventory drift; run python "
                "scripts/ci/generate_p8_l_p_evidence_response_streaming_inventory.py --write"
            )
        print("P8-L-P Evidence/response streaming inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-P inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
