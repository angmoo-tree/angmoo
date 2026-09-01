from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _inventory() -> dict:
    return json.loads(
        (
            ROOT / "docs/architecture/p8-l-h-canonical-recall-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_h_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_h_memory_recall_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_h_inventory_closes_recall_projection_and_non_scope() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-H"
    assert inventory["contract_version"] == "memory-recall.v1"
    assert inventory["canonical_schema"]["new_tables"] == []
    assert inventory["canonical_schema"]["new_migration"] is None
    assert inventory["private_projection"]["relative_path"] == (
        "search/memory-recall/generations/v1/angmoo-memory-recall.sqlite3"
    )
    assert inventory["private_projection"]["canonical"] is False
    assert inventory["private_projection"]["startup_rebuild"] is True
    assert inventory["private_projection"]["tombstones"] is True
    assert inventory["p5_feed_index"]["schema_changed"] is False
    assert inventory["p5_feed_index"]["document_loss_allowed"] == 0
    assert len(inventory["typed_operations"]) == 9
    assert inventory["domain_boundary"]["provider_dependency"] is None
    assert inventory["domain_boundary"]["planner_call_count"] == 0
    assert "ladybugdb_recall" in inventory["non_scope"]
    assert "character_response_generator" in inventory["non_scope"]
