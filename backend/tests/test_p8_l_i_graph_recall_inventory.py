from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _inventory() -> dict:
    return json.loads(
        (
            ROOT / "docs/architecture/p8-l-i-graph-recall-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_i_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_i_graph_recall_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_i_inventory_closes_facade_fallback_and_non_scope() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-I"
    assert inventory["contract_version"] == "graph-recall.v1"
    assert inventory["schema"]["new_alembic_migration"] is None
    assert inventory["schema"]["new_canonical_tables"] == []
    assert inventory["schema"]["new_ladybug_generation"] is None
    assert inventory["schema"]["sqlite_remains_canonical"] is True
    assert len(inventory["typed_operations"]) == 6
    assert inventory["hard_caps"]["path_hops"] == 3
    assert inventory["hard_caps"]["evidence_limit"] == 5
    assert inventory["domain_boundary"]["planner_call_count"] == 0
    assert inventory["domain_boundary"]["raw_sql_or_cypher_from_llm"] == 0
    assert inventory["degraded_policy"]["shortest_path"].startswith(
        "no_evidence"
    )
    assert "graph_retrieval_planner_llm" in inventory["non_scope"]
    assert "character_response_generator" in inventory["non_scope"]
