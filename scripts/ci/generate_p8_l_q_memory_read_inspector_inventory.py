"""Generate or verify the P8-L-Q Memory read and evidence-inspector inventory."""

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

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-q-memory-read-inspector-inventory.json"
P_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-p-evidence-response-streaming-inventory.json"
P_INVENTORY_SHA256 = "c802ddb544291cb29b113cb3ab3aad80fdda67fdc96d621eadb820bf3abb8cca"

from app.domains.chat.domain.evidence_bundle import MAX_EVIDENCE_ITEMS  # noqa: E402
from app.domains.memory.domain.read_surface import (  # noqa: E402
    MAX_MEMORY_READ_EVIDENCE_ITEMS,
    MAX_MEMORY_READ_PAGE_SIZE,
    MEMORY_READ_CONTRACT_VERSION,
)
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest  # noqa: E402
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402


class InventoryError(RuntimeError):
    pass


REQUIRED_FILES = (
    "backend/app/api/v1/main.py",
    "backend/app/api/v1/public.py",
    "backend/app/api/v1/routes/memory.py",
    "backend/app/api/v1/routes/world_chat_response.py",
    "backend/app/domains/chat/api/schemas.py",
    "backend/app/domains/chat/application/evidence_assembly.py",
    "backend/app/domains/chat/application/messages.py",
    "backend/app/domains/chat/application/response_workflow.py",
    "backend/app/domains/chat/domain/evidence_bundle.py",
    "backend/app/domains/chat/domain/response_request.py",
    "backend/app/domains/chat/infrastructure/response_lifecycle_repository.py",
    "backend/app/domains/chat/ports/runtime.py",
    "backend/app/domains/chat/public.py",
    "backend/app/domains/memory/api/schemas.py",
    "backend/app/domains/memory/application/read_surface.py",
    "backend/app/domains/memory/domain/read_surface.py",
    "backend/app/domains/memory/infrastructure/repository.py",
    "backend/app/domains/memory/ports/repository.py",
    "backend/app/domains/memory/public.py",
    "backend/app/runtime/chat/sqlalchemy_adapter.py",
    "backend/app/runtime/chat/sqlalchemy_service.py",
    "backend/app/runtime/chat/world_generation.py",
    "backend/security/public_route_security_inventory.json",
    "backend/security/route_security_inventory.json",
    "backend/tests/test_l3_er0_embedded_runtime_inventory.py",
    "backend/tests/test_l3_er5_tauri_product_shell_contract.py",
    "backend/tests/test_l4_pr_a_inventory.py",
    "backend/tests/test_m4_public_runtime.py",
    "backend/tests/test_p8_l_q_frontend_memory.py",
    "backend/tests/test_p8_l_q_memory_read_inspector.py",
    "browser-tests/product-shell.spec.ts",
    "browser-tests/static-product-shell.spec.ts",
    "desktop/platform/windows-host-tauri-dev.json",
    "desktop/src-tauri/capabilities/product-shell.json",
    "desktop/src-tauri/src/product_windows.rs",
    "desktop/src-tauri/tauri.contributor-docker.conf.json",
    "docs/architecture/backend-domains.md",
    "docs/architecture/frontend-design-baseline.json",
    "docs/architecture/frontend-design-reference.md",
    "docs/architecture/frontend-product-shell.md",
    "docs/architecture/migration-conversion-inventory.json",
    "docs/architecture/next-static-compatibility.json",
    "docs/architecture/p8-l-q-memory-read-inspector.md",
    "docs/architecture/postgres-sql-inventory.json",
    "frontend/DESIGN.md",
    "frontend/src/app/memory-explorer/page.tsx",
    "frontend/src/app/memory/page.tsx",
    "frontend/src/composition/static-product-router.tsx",
    "frontend/src/features/chat/api/world-chat-client.ts",
    "frontend/src/features/chat/model/world-chat-contract.ts",
    "frontend/src/features/chat/ui/world-chat.module.css",
    "frontend/src/features/chat/ui/world-chat.tsx",
    "frontend/src/features/device-home/model/device-home-contract.ts",
    "frontend/src/features/device-home/ui/device-home.tsx",
    "frontend/src/features/device-shell/model/device-navigation.ts",
    "frontend/src/features/memory/api/memory-client.ts",
    "frontend/src/features/memory/model/memory-contract.ts",
    "frontend/src/features/memory/public.ts",
    "frontend/src/features/memory/ui/memory-scope-summary.tsx",
    "frontend/src/features/memory/ui/memory-workspace.module.css",
    "frontend/src/features/memory/ui/memory-workspace.tsx",
    "frontend/src/features/memory/ui/world-chat-evidence-inspector.tsx",
    "frontend/src/shared/desktop/product-window.ts",
    "scripts/ci/check_windows_host_tauri_dev_contract.py",
    "scripts/ci/generate_p8_l_q_memory_read_inspector_inventory.py",
    "security/architecture_import_baseline.json",
    "security/frontend_architecture_policy.json",
    "security/frontend_design_policy.json",
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
        "backend/app/domains/memory/domain/read_surface.py",
        "backend/app/domains/memory/application/read_surface.py",
    ):
        _forbid_imports(
            relative,
            ("app.integrations", "app.runtime", "sqlalchemy", "fastapi"),
        )
    _require_text(
        "backend/app/domains/memory/application/read_surface.py",
        (
            "get_scope_setting(scope)",
            "fresh.source_digest == row.source_digest",
            "fresh.observed_by_subject",
            "fresh.membership_active",
            "not fresh.blocked",
            "fresh.visible",
            "fresh.successful",
        ),
    )
    _require_text(
        "backend/app/api/v1/routes/memory.py",
        (
            '@router.get("/memory/settings"',
            '@router.get("/memories"',
            '@router.get("/memories/{memory_id}"',
            "MemoryReadService",
        ),
    )
    _forbid_text(
        "backend/app/api/v1/routes/memory.py",
        ("@router.post", "@router.patch", "@router.put", "@router.delete"),
    )
    _require_text(
        "backend/app/domains/chat/infrastructure/response_lifecycle_repository.py",
        ('metadata_payload["_evidence_inspector_v1"]', "len(items) > 12"),
    )
    _require_text(
        "backend/app/runtime/chat/world_generation.py",
        (
            'if not key.startswith("_")',
            "fresh.observed_by_subject",
            "fresh.membership_active",
            "not fresh.blocked",
            "excerpt=text[:500] if availability == \"available\" else None",
        ),
    )
    _require_text(
        "frontend/src/features/memory/ui/memory-workspace.tsx",
        (
            'data-product-shell="memory"',
            "기억이 꺼져 있어요",
            "기존 기억은 읽을 수 있지만 새 기억은 쌓이지 않습니다.",
            "현재 확인 가능한 근거",
        ),
    )
    _require_text(
        "frontend/src/features/memory/ui/world-chat-evidence-inspector.tsx",
        ("data-world-chat-evidence-dialog", "이 답변의 근거", "canonical_href"),
    )
    _forbid_text(
        "frontend/src/features/memory/api/memory-client.ts",
        ('method: "POST"', 'method: "PATCH"', 'method: "PUT"', 'method: "DELETE"'),
    )
    return {
        "backend_domain_owner": "app.domains.memory",
        "chat_inspector_owner": "app.domains.chat",
        "frontend_feature": "frontend/src/features/memory",
        "domain_application_framework_imports": 0,
        "raw_sql_or_cypher_from_llm": 0,
        "read_surface_mutation_methods": 0,
        "source_revalidation_owner": "code",
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(P_INVENTORY_PATH) != P_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-P predecessor digest drift")
    predecessor = json.loads(P_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-P":
        raise InventoryError("P8-L-P predecessor owner drift")
    if SQLITE_SCHEMA_VERSION != 7:
        raise InventoryError("P8-L-Q must not advance Embedded schema v7")
    manifest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)

    return {
        "schema_version": 1,
        "owner_stage": "P8-L-Q",
        "contract_versions": {"memory_read": MEMORY_READ_CONTRACT_VERSION},
        "predecessor": _record(
            "docs/architecture/p8-l-p-evidence-response-streaming-inventory.json"
        ),
        "historical_chain": {
            "p8_l_p_sha256": P_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-Q",
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
        "read_contract": {
            "routes": [
                "GET /worlds/{world_id}/world-characters/{subject_id}/memory/settings",
                "GET /worlds/{world_id}/world-characters/{subject_id}/memories",
                "GET /worlds/{world_id}/world-characters/{subject_id}/memories/{memory_id}",
                "GET /worlds/{world_id}/chat/threads/{thread_id}/requests/{request_id}/evidence",
            ],
            "setting_get_side_effect_free": True,
            "missing_setting_defaults_enabled": False,
            "existing_memory_readable_while_off": True,
            "source_revalidated_at_read": True,
            "stale_source_excerpt_hidden": True,
            "public_raw_source_id": False,
            "public_prompt_query_token_provider_fields": False,
            "private_snapshot_namespace": "_evidence_inspector_v1",
            "normal_response_metadata_filters_private_keys": True,
        },
        "bounds": {
            "memory_evidence_items": MAX_MEMORY_READ_EVIDENCE_ITEMS,
            "memory_page_size": MAX_MEMORY_READ_PAGE_SIZE,
            "chat_evidence_items": MAX_EVIDENCE_ITEMS,
            "evidence_excerpt_characters": 500,
        },
        "frontend": {
            "canonical_route": "/memory",
            "legacy_redirect": "/memory-explorer -> /memory",
            "feature_owner": "features/memory",
            "wide_window_kind": "memory",
            "wide_window_singleton": True,
            "phone_window_accepts_memory_route": False,
            "narrow_browser_reflow_max_width": 799,
            "next_static_same_feature": True,
            "memory_mutations": [],
        },
        "executable_contract_gates": [
            "owner_world_subject_scope_isolation",
            "setting_get_has_zero_implicit_write",
            "memory_off_keeps_existing_read_surface",
            "bounded_list_and_detail_lifecycle",
            "current_canonical_source_revalidation",
            "deleted_stale_blocked_unobserved_excerpt_zero",
            "chat_summary_and_phone_dialog_inspector",
            "private_locator_not_in_normal_response_metadata",
            "next_static_memory_route_parity",
            "wide_tauri_memory_window_and_phone_rejection",
            "legacy_memory_explorer_redirect",
            "loading_empty_forbidden_not_found_degraded_error_surfaces",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "memory_on_off_mutation",
            "memory_pin_correction_delete",
            "actual_installer_user_gate",
            "held_out_causal_quality_closeout",
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
            raise InventoryError("generated P8-L-Q inventory is missing")
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-Q inventory drift; run python "
                "scripts/ci/generate_p8_l_q_memory_read_inspector_inventory.py --write"
            )
        print("P8-L-Q Memory read/inspector inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-Q inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
