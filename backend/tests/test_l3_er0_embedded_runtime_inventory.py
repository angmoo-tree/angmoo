from __future__ import annotations

import importlib.util

import json

from pathlib import Path

import subprocess

import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]

ARCHITECTURE = ROOT / "docs" / "architecture"

BASELINE = "db1c32510f66cee20a3e64a01e85c5ea8753d77e"

def _load(name: str) -> dict[str, object]:
    return json.loads((ARCHITECTURE / name).read_text(encoding="utf-8"))

def _checkpoint_postgres_inventory() -> dict[str, object]:
    """Keep the pre-refactor physical-file threshold tied to its Git snapshot."""
    source = subprocess.check_output(
        [
            "git", "show",
            "d7037625a19071eb279ad2ea35c3ace6fe5b5289:docs/architecture/postgres-sql-inventory.json",
        ],
        cwd=ROOT,
    )
    return json.loads(source)

def _postgres_generator(source_root: Path = ROOT):
    spec = importlib.util.spec_from_file_location(
        "angmoo_er0_current_postgres_inventory",
        ROOT / "scripts/verify_embedded_runtime_inventory.py",
    )
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    generator.ROOT = source_root
    return generator

def _assert_current_postgres_inventory(inventory: dict, *, source_root: Path = ROOT) -> None:
    """Every live marker, path, line and hash must match an unfiltered source scan."""
    source = _postgres_generator(source_root).build_postgres_inventory()
    assert inventory == source
    assert inventory["entry_count"] == len(inventory["entries"])
    assert len({entry["path"] for entry in inventory["entries"]}) == inventory["entry_count"]
    assert "historical schema evidence" in inventory["purpose"]
    assert "reintroduction guards" in inventory["purpose"]
    assert all(
        entry["markers"] and entry["owner"] and entry["transition_pr"] and entry["removal_condition"]
        for entry in inventory["entries"]
    )

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
    assert inventory["migration_count"] == 87
    assert len(entries) == len({entry["path"] for entry in entries}) == 87
    assert len(entries) == len({entry["revision"] for entry in entries}) == 87
    assert all(
        entry["owner"] == "ER2"
        and entry["transition_pr"] == "ER2 PR G"
        and entry["removal_condition"]
        for entry in entries
    )

def test_storage_frontend_runtime_and_parity_corpora_are_complete() -> None:
    # Splitting one original file into owned SQL and runtime queries changes
    # the physical total. Keep the old threshold on its immutable checkpoint;
    # validate every current entry against actual source independently.
    postgres = _checkpoint_postgres_inventory()
    _assert_current_postgres_inventory(_load("postgres-sql-inventory.json"))
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
