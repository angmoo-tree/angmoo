from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _inventory() -> dict:
    return json.loads(
        (
            ROOT / "docs/architecture/p8-l-k-retrieval-router-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_k_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_k_retrieval_router_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_k_inventory_closes_router_policy_and_clarification() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-K"
    assert inventory["predecessor"]["sha256"] == (
        "7479d1216aeeda010d88faa55fd045b8bcf887a757afc605b8d99526afa9fd45"
    )
    assert inventory["schema"]["new_alembic_migration"] is None
    assert inventory["domain_boundary"]["provider_prompt_canonical_ids"] == 0
    assert inventory["domain_boundary"]["test_live_provider_calls"] == 0
    assert inventory["clarification_policy"]["ambiguity_broadened_to_both"] is False
    assert inventory["clarification_policy"][
        "blocked_inactive_hidden_unobservable_candidates_exposed"
    ] == 0
    assert inventory["call_accounting"]["request_wide_schema_repair_max"] == 1
    assert inventory["call_accounting"]["generic_hidden_json_repair"] is False
    assert inventory["held_out_ko_contract"]["case_count"] == 315
    assert inventory["held_out_ko_contract"]["live_model_evaluation_completed"] is False
