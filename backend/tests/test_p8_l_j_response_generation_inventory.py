from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _inventory() -> dict:
    return json.loads(
        (
            ROOT
            / "docs/architecture/p8-l-j-response-generation-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_j_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_j_response_generation_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_j_inventory_closes_lifecycle_budget_and_non_scope() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-J"
    assert inventory["contract_versions"]["retrieval_intent"] == (
        "retrieval-intent.v1"
    )
    assert inventory["schema"]["new_alembic_migration"] == "20260831_0086"
    assert inventory["schema"]["new_embedded_schema_version"] == 6
    assert inventory["schema"]["new_canonical_tables"] == [
        "chat_response_requests"
    ]
    assert inventory["route_call_budgets"]["BOTH"]["normal_full_path"] == 4
    assert inventory["route_call_budgets"]["CURRENT_CONTEXT"][
        "normal_full_path"
    ] == 2
    assert inventory["call_accounting"][
        "character_response_generator_logical_max"
    ] == 1
    assert inventory["call_accounting"]["request_wide_schema_repair_max"] == 1
    assert inventory["lifecycle"]["assistant_and_metadata_and_commit_atomic"] is True
    assert inventory["canonical_response_request"]["raw_partial_delta_columns"] == 0
    assert inventory["domain_boundary"]["fake_executor_provider_calls"] == 0
    assert "live_character_response_generator_provider_adapter" in inventory[
        "non_scope"
    ]
