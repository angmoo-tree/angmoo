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
            / "docs/architecture/p8-l-n-both-workflow-coordinator-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_n_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_n_both_workflow_coordinator_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_n_inventory_closes_bounded_code_owned_both_coordination() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-N"
    assert inventory["predecessor"]["sha256"] == (
        "cb9354ca4441c585be054e49a1ba8d9046227cb4ebecfcbe9ec44f9830b569fe"
    )
    assert inventory["schema"]["new_alembic_migration"] is None
    assert set(inventory["recipe_registry"]) == {
        "INDEPENDENT_PARALLEL",
        "GRAPH_THEN_CANONICAL",
        "CANONICAL_THEN_GRAPH",
    }
    assert inventory["domain_boundary"]["coordinator_llm_nodes"] == 0
    assert inventory["domain_boundary"]["raw_sql_or_cypher"] == 0
    assert inventory["dependency_contract"][
        "zero_dependency_downstream_planner_short_circuit"
    ] is True
    assert inventory["deterministic_merge"]["dependent_intersection"] is True
    assert inventory["deterministic_merge"]["evidence_bundle_created"] is False
    assert inventory["call_accounting"]["both_normal_full_path_cap"] == 4
    assert inventory["call_accounting"]["coordinator_llm_calls"] == 0
    assert inventory["call_accounting"]["request_wide_schema_repair_max"] == 1
