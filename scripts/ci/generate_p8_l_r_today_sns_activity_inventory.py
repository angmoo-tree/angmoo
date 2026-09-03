"""Generate/verify the current-tree P8-L-R Today SNS context inventory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUTPUT = ROOT / "docs/architecture/p8-l-r-today-sns-activity-inventory.json"
PREDECESSOR = "docs/architecture/p8-l-r-memory-owner-control-inventory.json"
PREDECESSOR_SHA256 = "c02287d0d563582522a58c0ca9fd217b6b6985a59eafafa7b6278b6f8a818520"

from app.domains.chat.domain.call_tracker import NORMAL_NODE_BUDGETS  # noqa: E402
from app.domains.chat.domain.today_sns_activity import (  # noqa: E402
    MAX_TODAY_ENTRY_TEXT_CHARS, MAX_TODAY_ROUTER_ENTRIES,
    MAX_TODAY_ROUTER_VIEW_CHARS, TODAY_SNS_ACTIVITY_SNAPSHOT_VERSION,
)
from app.domains.social.domain.subjective_context import (  # noqa: E402
    ACTION_SUBJECTIVE_CONTEXT_VERSION, MAX_SUBJECTIVE_TEXT_CHARS,
    ActionEmotionLabel, ActionMotivationKind,
)
from app.domains.social.public import TodaySocialActivityKind  # noqa: E402
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest  # noqa: E402
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402
from app.runtime.social.sqlalchemy_today_activity import (  # noqa: E402
    MAX_TODAY_BRANCH_DEPTH, MAX_TODAY_QUERY_BATCH,
    MAX_TODAY_SOCIAL_RECORDS, MAX_TODAY_SOCIAL_SCAN,
)

REQUIRED_FILES = (
    ".github/workflows/windows-installer.yml",
    "backend/app/alembic/versions/20260904_0088_social_action_subjective_context.py",
    "backend/app/domains/chat/api/schemas.py",
    "backend/app/domains/chat/application/evidence_assembly.py",
    "backend/app/domains/chat/application/response_workflow.py",
    "backend/app/domains/chat/application/retrieval_routing.py",
    "backend/app/domains/chat/application/today_sns_activity.py",
    "backend/app/domains/chat/domain/evidence_bundle.py",
    "backend/app/domains/chat/domain/retrieval_intent.py",
    "backend/app/domains/chat/domain/retrieval_router.py",
    "backend/app/domains/chat/domain/today_sns_activity.py",
    "backend/app/domains/chat/ports/character_response_generator.py",
    "backend/app/domains/chat/ports/retrieval_router_provider.py",
    "backend/app/domains/chat/ports/today_sns_activity.py",
    "backend/app/domains/routine_posts/api/schemas.py",
    "backend/app/domains/routine_posts/infrastructure/direct_llm_provider.py",
    "backend/app/domains/social/domain/subjective_context.py",
    "backend/app/domains/social/domain/today_activity.py",
    "backend/app/domains/social/infrastructure/sqlalchemy_subjective_context_models.py",
    "backend/app/domains/social/public.py",
    "backend/app/integrations/llm/character_response_generator.py",
    "backend/app/integrations/llm/retrieval_router.py",
    "backend/app/runtime/chat/today_sns_activity.py",
    "backend/app/runtime/chat/world_generation.py",
    "backend/app/runtime/migrations/sqlite_versions/manifests/v8.json",
    "backend/app/runtime/migrations/sqlite_versions/v7_to_v8_social_action_subjective_context.py",
    "backend/app/runtime/persistence/sqlite_schema.py",
    "backend/app/runtime/routine_posts/sqlalchemy_runtime.py",
    "backend/app/runtime/social/sqlalchemy_today_activity.py",
    "backend/app/runtime/social/sqlalchemy_read_repository.py",
    "backend/app/runtime/social/subjective_context.py",
    "backend/app/schemas/world_feed.py",
    "backend/app/services/feed_reaction_planner.py",
    "backend/app/services/auth.py",
    "backend/app/services/world_character_setup.py",
    "backend/app/services/langgraph_resident.py",
    "backend/app/services/langgraph_social_apply.py",
    "backend/app/services/world_feed_runtime.py",
    "backend/app/services/world_feed_social_apply.py",
    "backend/tests/test_p8_l_r_today_sns_activity.py",
    "backend/tests/test_p8_l_r_today_sns_activity_inventory.py",
    "backend/tests/test_p8_l_r_today_sns_activity_migration.py",
    "backend/tests/test_p8_l_p_evidence_response_streaming.py",
    "backend/security/privacy_deletion_inventory.json",
    "browser-tests/product-shell.spec.ts",
    "browser-tests/static-product-shell.spec.ts",
    "docs/architecture/backend-domains.md",
    "docs/architecture/frontend-design-reference.md",
    "docs/architecture/frontend-product-shell.md",
    "docs/architecture/p8-l-r-today-sns-activity.md",
    "frontend/DESIGN.md",
    "frontend/src/features/memory/api/memory-client.ts",
    "frontend/src/features/memory/model/memory-contract.ts",
    "frontend/src/features/memory/ui/memory-workspace.tsx",
    "scripts/ci/generate_p8_l_r_memory_owner_control_inventory.py",
    "scripts/ci/generate_p8_l_j_response_generation_inventory.py",
    "scripts/ci/generate_p8_l_k_retrieval_router_inventory.py",
    "scripts/ci/generate_p8_l_l_canonical_retrieval_planner_inventory.py",
    "scripts/ci/generate_p8_l_m_graph_retrieval_planner_inventory.py",
    "scripts/ci/generate_p8_l_n_both_workflow_coordinator_inventory.py",
    "scripts/ci/generate_p8_l_o_memory_consolidation_inventory.py",
    "scripts/ci/generate_p8_l_p_evidence_response_streaming_inventory.py",
    "scripts/ci/build_windows_installer_supported_upgrade_fixture.py",
    "scripts/ci/check_windows_installer_supported_upgrade_matrix.py",
    "scripts/ci/run_windows_installer_supported_upgrade.ps1",
    "scripts/ci/generate_p8_l_r_today_sns_activity_inventory.py",
)


def _record(relative):
    data = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
    return {"path": relative, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _require(relative, *values):
    text = (ROOT / relative).read_text(encoding="utf-8")
    if any(value not in text for value in values):
        raise ValueError(f"missing Today contract in {relative}")


def _boundaries():
    for relative in (
        "backend/app/domains/social/domain/subjective_context.py",
        "backend/app/domains/social/domain/today_activity.py",
        "backend/app/domains/chat/domain/today_sns_activity.py",
        "backend/app/domains/chat/application/today_sns_activity.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
        for name in imports:
            if name.startswith(("app.runtime", "app.integrations", "sqlalchemy", "fastapi")):
                raise ValueError(f"framework/provider boundary violation: {relative}: {name}")
    _require("backend/app/domains/chat/application/response_workflow.py",
             "today_sns_snapshot.router_view()", "assert_current(command.today_sns_snapshot)",
             "source_context_changed")
    _require("backend/app/runtime/social/sqlalchemy_today_activity.py",
             "counts_exact=not scan_overflow", "_execution_matches",
             "subjective_context_digest", "represented_posts")
    _require("backend/app/runtime/chat/world_generation.py",
             '"today_sns_activity": "오늘 SNS 활동"', "source_revision",
             "SqlAlchemyTodaySnsSnapshotValidator")
    _require("frontend/src/features/memory/model/memory-contract.ts", '"today_sns_activity"')
    _require("frontend/src/features/memory/api/memory-client.ts", '"today_sns_activity"')
    _require("frontend/src/features/memory/ui/memory-workspace.tsx", "오늘의 World SNS 활동")
    return {"social_contract_owner": "domains/social", "snapshot_owner": "domains/chat",
            "query_and_action_transaction_owner": "runtime/social",
            "frontend_feature": "features/memory", "framework_imports_in_pure_contracts": 0}


def build_inventory():
    predecessor = _record(PREDECESSOR)
    if predecessor["sha256"] != PREDECESSOR_SHA256:
        raise ValueError("frozen P8-L-R owner-control predecessor drift")
    if SQLITE_SCHEMA_VERSION != 8:
        raise ValueError("Today SNS requires embedded SQLite v8")
    manifest = load_sqlite_manifest(8)
    if manifest.source_revision != "20260904_0088" or manifest.canonical_table_count != 96:
        raise ValueError("Today SNS schema lineage drift")
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-R-TODAY",
        "predecessor": predecessor,
        "contract_versions": {
            "snapshot": TODAY_SNS_ACTIVITY_SNAPSHOT_VERSION,
            "subjective_context": ACTION_SUBJECTIVE_CONTEXT_VERSION,
        },
        "schema": {
            "embedded_schema_version": SQLITE_SCHEMA_VERSION,
            "source_revision": manifest.source_revision,
            "source_migration_count": manifest.source_migration_count,
            "canonical_table_count": manifest.canonical_table_count,
            "schema_digest": manifest.schema_digest,
            "new_tables": ["social_action_subjective_contexts"],
            "legacy_inferred_backfill": 0,
            "ladybug_schema_change": False,
        },
        "boundaries": _boundaries(),
        "catalog": {
            "activity_kinds": list(TodaySocialActivityKind.values()),
            "motivation_kinds": list(ActionMotivationKind.values()),
            "emotion_labels": list(ActionEmotionLabel.values()),
        },
        "bounds": {
            "source_scan": MAX_TODAY_SOCIAL_SCAN,
            "query_batch": MAX_TODAY_QUERY_BATCH,
            "branch_depth": MAX_TODAY_BRANCH_DEPTH,
            "snapshot_records": MAX_TODAY_SOCIAL_RECORDS,
            "router_entries": MAX_TODAY_ROUTER_ENTRIES,
            "router_view_characters": MAX_TODAY_ROUTER_VIEW_CHARS,
            "body_characters": MAX_TODAY_ENTRY_TEXT_CHARS,
            "subjective_text_characters": MAX_SUBJECTIVE_TEXT_CHARS,
        },
        "runtime_contract": {
            "today_assembler_provider_calls": 0,
            "normal_route_calls": {route.value: sum(nodes.values()) for route, nodes in NORMAL_NODE_BUDGETS.items()},
            "memory_off_allows_today_context": True,
            "private_other_thread_context": False,
            "other_actor_private_motivation": False,
            "snapshot_mapping_immutable": True,
            "pre_response_and_pre_commit_revalidation": True,
            "later_activity_inserted_into_active_snapshot": False,
            "scan_overflow_count_semantics": "lower_bound_with_partial_coverage",
            "owner_inspector_exact_revision_revalidation": True,
        },
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "remaining_user_gates": [
            "installed_post_to_chat", "installed_reply_inbound_reply_to_chat",
            "installed_declared_motivation_emotion", "installed_memory_off",
            "held_out_quality_latency", "user_merge", "post_merge_actions",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        rendered = json.dumps(build_inventory(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.write:
            OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
        elif OUTPUT.read_text(encoding="utf-8").replace("\r\n", "\n") != rendered:
            raise ValueError("Today SNS inventory drift; regenerate with --write")
        print("P8-L-R Today SNS activity inventory is current")
        return 0
    except (OSError, ValueError, KeyError, SyntaxError) as exc:
        print(f"Today SNS inventory failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
