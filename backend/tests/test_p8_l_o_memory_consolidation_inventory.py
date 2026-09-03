from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _inventory() -> dict:
    return json.loads(
        (
            ROOT / "docs/architecture/p8-l-o-memory-consolidation-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_o_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_o_memory_consolidation_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_o_inventory_closes_background_memory_budget() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-O"
    assert inventory["predecessor"]["sha256"] == (
        "7b9158f4c6461cf197b5d792ece3ca5bf80453a103534b6398b7868ad2a10b19"
    )
    assert inventory["schema"]["new_alembic_migration"] is None
    assert inventory["schema"]["current_embedded_schema_version"] == 6
    assert inventory["threshold_policy"]["pending_candidate_count"] == 8
    assert inventory["bounds"]["provider_calls_per_claimed_batch"] == 1
    assert inventory["bounds"]["provider_hidden_overload_retries"] == 0
    assert inventory["bounds"]["maintenance_attempts"] == 3
    assert inventory["failure_contract"]["memory_off_provider_calls"] == 0
    assert inventory["failure_contract"][
        "provider_failure_deterministic_fallback"
    ] is True
    assert inventory["failure_contract"][
        "sub_threshold_batch_tail_continuation"
    ] is True
    assert inventory["hot_brief_contract"]["exact_item_version_links"] is True
    assert inventory["domain_boundary"][
        "foreground_route_aware_call_tracker_imports"
    ] == 0
