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
            / "docs/architecture/p8-l-q-memory-read-inspector-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_q_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_q_memory_read_inspector_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_q_inventory_closes_read_only_memory_and_inspector_contract() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-Q"
    assert inventory["predecessor"]["sha256"] == (
        "c802ddb544291cb29b113cb3ab3aad80fdda67fdc96d621eadb820bf3abb8cca"
    )
    assert inventory["schema"]["current_embedded_schema_version"] == 7
    assert inventory["schema"]["new_alembic_migration"] is None
    assert inventory["schema"]["new_embedded_schema_version"] is None
    assert inventory["schema"]["new_ladybug_generation"] is None
    assert inventory["bounds"] == {
        "chat_evidence_items": 12,
        "evidence_excerpt_characters": 500,
        "memory_evidence_items": 50,
        "memory_page_size": 50,
    }
    read_contract = inventory["read_contract"]
    assert read_contract["setting_get_side_effect_free"] is True
    assert read_contract["missing_setting_defaults_enabled"] is False
    assert read_contract["existing_memory_readable_while_off"] is True
    assert read_contract["source_revalidated_at_read"] is True
    assert read_contract["stale_source_excerpt_hidden"] is True
    assert read_contract["public_raw_source_id"] is False
    assert read_contract["public_prompt_query_token_provider_fields"] is False
    assert read_contract["normal_response_metadata_filters_private_keys"] is True
    assert inventory["frontend"]["canonical_route"] == "/memory"
    assert inventory["frontend"]["wide_window_kind"] == "memory"
    assert inventory["frontend"]["phone_window_accepts_memory_route"] is False
    assert inventory["frontend"]["memory_mutations"] == []
    assert inventory["domain_boundary"]["read_surface_mutation_methods"] == 0
