"""Generate or verify the P8-L-O Memory consolidation inventory."""

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

OUTPUT_PATH = ROOT / "docs/architecture/p8-l-o-memory-consolidation-inventory.json"
N_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-n-both-workflow-coordinator-inventory.json"
N_INVENTORY_SHA256 = "b897cab121274c4c446602c0481b01514fead9607fe36c4569f416dd2d3d2ecf"

from app.domains.memory.domain import (  # noqa: E402
    MAINTENANCE_LEASE_DURATION,
    MAX_HOT_BRIEF_SOURCE_ITEMS,
    MAX_HOT_BRIEF_SUMMARY_LENGTH,
    MAX_MAINTENANCE_ATTEMPTS,
    MAX_MAINTENANCE_BATCH_CANDIDATES,
    MAX_MAINTENANCE_PROVIDER_INPUT_CHARACTERS,
    MAX_SHUTDOWN_DRAIN_JOBS,
    MEMORY_CONSOLIDATION_CONTRACT_VERSION,
    MEMORY_CONSOLIDATION_POLICY_V1,
    MEMORY_CONSOLIDATION_PROVIDER_OUTPUT_VERSION,
    MEMORY_HOT_BRIEF_CONTRACT_VERSION,
)
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION  # noqa: E402


class InventoryError(RuntimeError):
    pass


REQUIRED_FILES = (
    "backend/app/domains/memory/application/consolidation.py",
    "backend/app/domains/memory/domain/consolidation.py",
    "backend/app/domains/memory/domain/consolidation_provider.py",
    "backend/app/domains/memory/infrastructure/consolidation_repository.py",
    "backend/app/domains/memory/infrastructure/maintenance_queue.py",
    "backend/app/domains/memory/infrastructure/maintenance_unit_of_work.py",
    "backend/app/domains/memory/ports/consolidation_provider.py",
    "backend/app/domains/memory/ports/consolidation_repository.py",
    "backend/app/domains/memory/ports/maintenance_unit_of_work.py",
    "backend/app/domains/memory/public.py",
    "backend/app/integrations/llm/memory_consolidation.py",
    "backend/tests/test_p8_l_o_memory_consolidation.py",
    "backend/tests/test_p8_l_o_memory_consolidation_inventory.py",
    "docs/architecture/backend-domains.md",
    "docs/architecture/p8-l-o-memory-consolidation-hot-brief.md",
    "scripts/ci/generate_p8_l_o_memory_consolidation_inventory.py",
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


def _boundary_contract() -> dict[str, Any]:
    _forbid_imports(
        "backend/app/domains/memory/domain/consolidation.py",
        ("app.integrations", "app.runtime", "sqlalchemy", "fastapi"),
    )
    _forbid_imports(
        "backend/app/domains/memory/application/consolidation.py",
        ("app.integrations", "app.runtime", "sqlalchemy", "fastapi"),
    )
    _require_text(
        "backend/app/domains/memory/application/consolidation.py",
        (
            "memory_evidence_blocked_code",
            "enqueue_maintenance=False",
            "provider_result.physical_call_count != 1",
            "MAX_MAINTENANCE_ATTEMPTS",
            "MAX_SHUTDOWN_DRAIN_JOBS",
            "batch_continuation",
            "continuation_job_id",
            "MemoryMaintenanceLane.IMMEDIATE",
            "deterministic_hot_brief",
        ),
    )
    _require_text(
        "backend/app/integrations/llm/memory_consolidation.py",
        (
            "get_provider_adapter",
            "await self._adapter.generate_json(provider_request)",
            "performs one provider transport attempt",
            "candidate_ref",
            "deterministic_summary",
        ),
    )
    _forbid_imports(
        "backend/app/integrations/llm/memory_consolidation.py",
        ("app.integrations.direct_llm",),
    )
    _require_text(
        "backend/app/domains/memory/infrastructure/consolidation_repository.py",
        (
            "memory_item_set_digest",
            "memory_item_high_watermark",
            "memory_hot_brief_source_version_conflict",
            "MemoryHotBriefItem",
            "MemoryHotBriefStatus.SUPERSEDED",
        ),
    )
    return {
        "owner": "app.domains.memory",
        "optional_provider_adapter": "app.integrations.llm.memory_consolidation",
        "provider_output": "summary_proposal_only",
        "provider_actual_canonical_ids": 0,
        "provider_raw_private_transcripts": 0,
        "foreground_route_aware_call_tracker_imports": 0,
        "raw_sql_or_cypher": 0,
        "application_runtime_or_orm_imports": 0,
        "test_live_provider_calls": 0,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(N_INVENTORY_PATH) != N_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-N predecessor digest drift")
    predecessor = json.loads(N_INVENTORY_PATH.read_text(encoding="utf-8"))
    if predecessor["owner_stage"] != "P8-L-N":
        raise InventoryError("P8-L-N predecessor owner drift")
    if SQLITE_SCHEMA_VERSION != 6:
        raise InventoryError("P8-L-O must not change Embedded schema version")

    policy = MEMORY_CONSOLIDATION_POLICY_V1
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-O",
        "contract_versions": {
            "consolidation": MEMORY_CONSOLIDATION_CONTRACT_VERSION,
            "hot_brief": MEMORY_HOT_BRIEF_CONTRACT_VERSION,
            "provider_output": MEMORY_CONSOLIDATION_PROVIDER_OUTPUT_VERSION,
        },
        "predecessor": _record(
            "docs/architecture/p8-l-n-both-workflow-coordinator-inventory.json"
        ),
        "historical_chain": {
            "p8_l_n_sha256": N_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-O",
        },
        "schema": {
            "new_alembic_migration": None,
            "new_embedded_schema_version": None,
            "current_embedded_schema_version": SQLITE_SCHEMA_VERSION,
            "new_canonical_tables": [],
            "new_ladybug_generation": None,
            "reused_tables": [
                "memory_scope_settings",
                "memory_candidates",
                "memory_items",
                "memory_item_evidence",
                "memory_hot_briefs",
                "memory_hot_brief_items",
                "memory_maintenance_jobs",
            ],
        },
        "domain_boundary": _boundary_contract(),
        "threshold_policy": {
            "pending_candidate_count": policy.pending_candidate_threshold,
            "pending_summary_characters": policy.pending_character_threshold,
            "minimum_interval_seconds": int(policy.minimum_interval.total_seconds()),
            "active_item_refresh_count": policy.active_item_refresh_threshold,
            "production_values_hidden_in_environment": False,
            "change_requires_contract_inventory_pr": True,
        },
        "bounds": {
            "candidate_batch": MAX_MAINTENANCE_BATCH_CANDIDATES,
            "hot_brief_source_items": MAX_HOT_BRIEF_SOURCE_ITEMS,
            "hot_brief_summary_characters": MAX_HOT_BRIEF_SUMMARY_LENGTH,
            "provider_input_characters": MAX_MAINTENANCE_PROVIDER_INPUT_CHARACTERS,
            "provider_calls_per_claimed_batch": 1,
            "provider_hidden_overload_retries": 0,
            "provider_hidden_json_repairs": 0,
            "maintenance_attempts": MAX_MAINTENANCE_ATTEMPTS,
            "lease_seconds": int(MAINTENANCE_LEASE_DURATION.total_seconds()),
            "shutdown_drain_jobs": MAX_SHUTDOWN_DRAIN_JOBS,
        },
        "hot_brief_contract": {
            "derived_cache": True,
            "exact_item_version_links": True,
            "source_item_set_digest": True,
            "source_item_high_watermark": True,
            "generation_monotonic": True,
            "source_version_fence": True,
            "off_invalidates_active": True,
            "rebuildable_from_canonical_items": True,
        },
        "failure_contract": {
            "memory_off_provider_calls": 0,
            "pre_threshold_provider_calls": 0,
            "provider_failure_deterministic_fallback": True,
            "provider_failure_blocks_basic_chat": False,
            "provider_failure_deletes_canonical_items": False,
            "source_revalidation_before_provider": True,
            "source_revalidation_before_item_write": True,
            "lease_renewal": True,
            "same_scope_serialization": True,
            "bounded_retry": True,
            "bounded_shutdown_drain": True,
            "sub_threshold_batch_tail_continuation": True,
        },
        "executable_contract_gates": [
            "ordinary_pre_threshold_provider_zero",
            "threshold_idempotent_enqueue",
            "automatic_batch_provider_max_one",
            "immediate_lane_separate_provider_max_one",
            "provider_failure_deterministic_item_and_brief",
            "memory_off_provider_and_processing_zero",
            "source_scope_visibility_membership_block_observation_revalidation",
            "candidate_replay_no_duplicate_item",
            "hot_brief_generation_and_exact_item_version_fence",
            "off_invalidates_active_hot_brief",
            "leased_retry_max_three",
            "shutdown_drain_deadline_and_cap",
            "batch_tail_continuation_until_pending_zero",
            "direct_adapter_hidden_retry_zero",
        ],
        "required_files": [_record(relative) for relative in REQUIRED_FILES],
        "non_scope": [
            "live_chat_after_commit_candidate_producer",
            "evidence_bundle_snapshot",
            "character_response_generator",
            "typing_presence_or_streaming_ui",
            "memory_read_or_control_ui",
            "live_provider_quality_or_latency_pass",
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
            raise InventoryError("generated P8-L-O inventory is missing")
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-O inventory drift; run python "
                "scripts/ci/generate_p8_l_o_memory_consolidation_inventory.py --write"
            )
        print("P8-L-O Memory consolidation inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, ValueError) as exc:
        print(f"P8-L-O inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
