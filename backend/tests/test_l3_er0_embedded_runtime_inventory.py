from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "docs" / "architecture"
BASELINE = "db1c32510f66cee20a3e64a01e85c5ea8753d77e"


def _load(name: str) -> dict[str, object]:
    return json.loads((ARCHITECTURE / name).read_text(encoding="utf-8"))


def test_generated_embedded_runtime_inventory_is_current() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/verify_embedded_runtime_inventory.py", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_all_migrations_are_owned_exactly_once() -> None:
    inventory = _load("migration-conversion-inventory.json")
    entries = inventory["entries"]
    assert inventory["baseline_commit"] == BASELINE
    assert inventory["migration_count"] == 86
    assert len(entries) == len({entry["path"] for entry in entries}) == 86
    assert len(entries) == len({entry["revision"] for entry in entries}) == 86
    assert all(
        entry["owner"] == "ER2"
        and entry["transition_pr"] == "ER2 PR G"
        and entry["removal_condition"]
        for entry in entries
    )


def test_storage_frontend_runtime_and_parity_corpora_are_complete() -> None:
    postgres = _load("postgres-sql-inventory.json")
    graph = _load("neo4j-query-corpus.json")
    frontend = _load("next-static-compatibility.json")
    runtime = _load("embedded-runtime-inventory.json")

    # PR P removes PostgreSQL/Neo4j from every public and contributor runtime.
    # PostgreSQL markers may remain only in historical Alembic evidence,
    # serialized compatibility values, and negative reintroduction guards.
    # The active importer is gone, so the inventory must explain the
    # residual-only purpose explicitly.
    assert 0 < postgres["entry_count"] < 82
    assert "historical schema evidence" in postgres["purpose"]
    assert "reintroduction guards" in postgres["purpose"]
    assert graph["query_count"] == 24
    assert frontend["route_count"] == 44
    assert {item["phase"] for item in runtime["parity"]["workloads"]} == {
        "P1", "P2", "P3", "P4", "P5", "P6", "P7"
    }
    assert all(not item["missing_tests"] for item in runtime["parity"]["workloads"])
    assert len(runtime["runtime_coupling"]) == 9
    assert all(
        item["owner"] and item["transition_pr"] and item["removal_condition"]
        for item in runtime["runtime_coupling"]
    )


def test_er0_records_behavior_zero_and_privacy_safe_resource_evidence() -> None:
    adr = (ARCHITECTURE / "embedded-runtime-adr.md").read_text(encoding="utf-8")
    summary = (ARCHITECTURE / "embedded-runtime-inventory.md").read_text(encoding="utf-8")
    resources = _load("embedded-runtime-resource-baseline.json")

    assert "ER0 does not add SQLite, LadybugDB" in adr
    assert "ER0 baseline behavior change: **zero**" in summary
    assert resources["services"]["healthy"] == 6
    assert resources["volumes"]["canonical_count"] == 5
    serialized = json.dumps(resources, ensure_ascii=False).lower()
    assert "app_secret" not in serialized
    assert "d:\\" not in serialized
