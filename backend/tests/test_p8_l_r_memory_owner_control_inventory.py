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
            / "docs/architecture/p8-l-r-memory-owner-control-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_r_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_r_memory_owner_control_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_r_inventory_closes_owner_control_without_schema_change() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-R"
    assert inventory["predecessor"]["sha256"] == (
        "543f8f2457abbc03f50b7e0cace5fa8edffe680c74df53379fa21da588da9611"
    )
    assert inventory["schema"]["current_embedded_schema_version"] == 7
    assert inventory["schema"]["new_alembic_migration"] is None
    assert inventory["schema"]["new_embedded_schema_version"] is None
    assert inventory["schema"]["new_ladybug_generation"] is None
    assert inventory["bounds"] == {
        "correction_summary_characters": 2_000,
        "narrow_browser_reflow_max_width": 799,
        "simultaneous_workspace_mutations": 1,
    }
    mutation = inventory["mutation_contract"]
    assert len(mutation["routes"]) == 4
    assert mutation["memory_off_keeps_existing_items_readable"] is True
    assert mutation["memory_off_allows_pin_unpin_and_delete"] is True
    assert mutation["memory_off_allows_correction"] is False
    assert mutation["correction_revalidates_every_evidence_source"] is True
    assert mutation["delete_blocks_retrieval_in_canonical_transaction"] is True
    assert mutation["projection_cleanup"] == "automatic_after_commit"
    assert mutation["provider_calls"] == 0
    assert inventory["frontend"]["controls"] == [
        "on_off",
        "pin_unpin",
        "correction",
        "delete",
    ]
    assert inventory["domain_boundary"]["raw_sql_or_cypher_in_route"] == 0
