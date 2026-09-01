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
            / "docs/architecture/p8-l-f-canonical-memory-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_f_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_f_memory_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_f_inventory_closes_schema_scope_and_non_scope() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-F"
    assert inventory["domain_boundary"] == {
        "backend_ownership": "domains/memory",
        "provider_calls": 0,
        "public_facade": "app.domains.memory.public",
        "raw_sql_or_cypher_from_llm": 0,
        "ports": [
            "MemoryRepositoryPort",
            "MemorySourceEvidenceReaderPort",
            "MemoryMaintenanceQueuePort",
        ],
    }
    assert inventory["memory_kind_v1"] == [
        "OWNER_PREFERENCE",
        "AUTOBIOGRAPHICAL_EVENT",
        "DIRECTIONAL_RELATIONSHIP",
        "THREAD_SUMMARY",
        "ACCEPTED_JOINT_COMMITMENT",
    ]
    assert inventory["schema"]["default_enabled"] is False
    assert inventory["schema"]["default_retention_days"] == 180
    assert inventory["schema"]["scope"] == [
        "owner_id",
        "world_id",
        "subject_world_character_id",
    ]
    assert len(inventory["schema"]["tables"]) == 7
    assert inventory["migration"]["alembic_revision"] == "20260831_0085"
    assert inventory["migration"]["embedded_sqlite"]["schema_version"] == 5
    assert inventory["migration"]["embedded_sqlite"]["canonical_table_count"] == 94
    assert inventory["installer_upgrade"]["supported_predecessors"] == [1, 2, 3, 4]
    assert "candidate_provider" in inventory["non_scope"]
    assert "fts5_retrieval" in inventory["non_scope"]
    assert "graph_retrieval" in inventory["non_scope"]
