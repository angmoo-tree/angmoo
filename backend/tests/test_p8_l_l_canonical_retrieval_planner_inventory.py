from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _inventory() -> dict:
    return json.loads(
        (
            ROOT
            / "docs/architecture/p8-l-l-canonical-retrieval-planner-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_l_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_l_canonical_retrieval_planner_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_l_inventory_closes_canonical_planner_and_typed_execution() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-L"
    assert inventory["predecessor"]["sha256"] == (
        "4d98b3d04d31fd821b9f63901c1521d4652b33e59b77b15f0ad22ce8d65b7a2b"
    )
    assert inventory["schema"]["new_alembic_migration"] is None
    assert inventory["provider_schema"]["operation_count"] == 9
    assert inventory["provider_schema"]["graph_operations"] == 0
    assert inventory["domain_boundary"]["provider_prompt_canonical_ids"] == 0
    assert inventory["domain_boundary"]["test_live_provider_calls"] == 0
    assert inventory["code_owned_execution"]["row_hard_cap"] is True
    assert inventory["code_owned_execution"][
        "fts_candidate_canonical_revalidation"
    ] is True
    assert inventory["call_accounting"]["canonical_normal_full_path_cap"] == 3
    assert inventory["call_accounting"]["request_wide_schema_repair_max"] == 1
    assert inventory["call_accounting"]["generic_hidden_json_repair"] is False
    assert inventory["held_out_ko_contract"]["case_count"] == 36
    assert inventory["held_out_ko_contract"]["live_model_evaluation_completed"] is False
