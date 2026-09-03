from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _inventory() -> dict:
    return json.loads(
        (
            ROOT / "docs/architecture/p8-l-m-graph-retrieval-planner-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_m_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_m_graph_retrieval_planner_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_m_inventory_closes_graph_planner_and_typed_execution() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-M"
    assert inventory["predecessor"]["sha256"] == (
        "3c878fce03c67a44b42c0474d4359a1b669a15fd97e90358ea1009686943ff27"
    )
    assert inventory["schema"]["new_alembic_migration"] is None
    assert inventory["provider_schema"]["operation_count"] == 6
    assert inventory["provider_schema"]["canonical_operations"] == 0
    assert inventory["domain_boundary"]["provider_prompt_canonical_ids"] == 0
    assert inventory["domain_boundary"]["test_live_provider_calls"] == 0
    assert inventory["code_owned_execution"]["hop_hard_cap"] is True
    assert inventory["code_owned_execution"]["fanout_hard_cap"] is True
    assert inventory["code_owned_execution"][
        "ladybug_candidate_canonical_revalidation"
    ] is True
    assert inventory["call_accounting"]["graph_normal_full_path_cap"] == 3
    assert inventory["call_accounting"]["request_wide_schema_repair_max"] == 1
    assert inventory["call_accounting"]["generic_hidden_json_repair"] is False
    assert inventory["held_out_ko_contract"]["case_count"] == 36
    assert inventory["held_out_ko_contract"]["live_model_evaluation_completed"] is False
