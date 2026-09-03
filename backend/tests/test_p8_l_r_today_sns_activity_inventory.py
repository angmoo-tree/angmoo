from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_today_sns_inventory_is_current():
    result = subprocess.run(
        [sys.executable, "scripts/ci/generate_p8_l_r_today_sns_activity_inventory.py", "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_today_sns_inventory_preserves_route_budget_and_memory_off_semantics():
    inventory = json.loads((ROOT / "docs/architecture/p8-l-r-today-sns-activity-inventory.json").read_text(encoding="utf-8"))
    assert inventory["owner_stage"] == "P8-L-R-TODAY"
    assert inventory["schema"]["embedded_schema_version"] == 8
    assert inventory["schema"]["canonical_table_count"] == 96
    assert inventory["schema"]["legacy_inferred_backfill"] == 0
    contract = inventory["runtime_contract"]
    assert contract["today_assembler_provider_calls"] == 0
    assert contract["normal_route_calls"] == {
        "CURRENT_CONTEXT": 2, "CANONICAL": 3, "GRAPH": 3, "BOTH": 4, "CLARIFICATION": 2,
    }
    assert contract["memory_off_allows_today_context"] is True
    assert contract["pre_response_and_pre_commit_revalidation"] is True
    assert contract["other_actor_private_motivation"] is False
    assert inventory["boundaries"]["framework_imports_in_pure_contracts"] == 0
