from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _inventory() -> dict:
    return json.loads(
        (
            ROOT / "docs/architecture/p8-l-g-memory-write-lifecycle-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_g_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_g_memory_write_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_g_inventory_closes_write_lifecycle_and_non_scope() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-G"
    assert inventory["contract_version"] == "memory-write.v1"
    assert inventory["schema"]["new_tables"] == []
    assert inventory["schema"]["new_migration"] is None
    assert inventory["domain_boundary"]["provider_dependency"] is None
    assert inventory["domain_boundary"]["ordinary_turn_provider_call_count"] == 0
    assert inventory["lifecycle"]["same_scope_serialization"] is True
    assert inventory["lifecycle"]["pin_bypasses_expiry_only"] is True
    gates = {
        item["fixture_id"]: item["expected"]
        for item in inventory["executable_contract_gates"]
    }
    assert gates["memory_opt_out_blocked"]["writes"] == []
    assert gates["memory_opt_out_blocked"]["provider_call_count"] == 0
    assert gates["memory_deleted_blocked"]["code"] == "memory_not_retrievable"
    assert "fts5_projection_and_recall" in inventory["non_scope"]
    assert "maintenance_llm_provider" in inventory["non_scope"]
