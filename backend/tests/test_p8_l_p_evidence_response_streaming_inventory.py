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
            / "docs/architecture/p8-l-p-evidence-response-streaming-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_p_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_p_evidence_response_streaming_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_p_inventory_closes_streaming_and_after_commit_contract() -> None:
    inventory = _inventory()
    assert inventory["owner_stage"] == "P8-L-P"
    assert inventory["predecessor"]["sha256"] == (
        "ff10df3e8a6c9e222c7a88c206d9dbbdefc7ba49c753a875bcdb721d02d3c055"
    )
    assert inventory["schema"]["current_embedded_schema_version"] == 7
    assert inventory["schema"]["new_alembic_migration"] == "20260903_0087"
    assert inventory["model_hotfix"]["binding_modes"] == [
        "default",
        "thread_override",
    ]
    assert inventory["bounds"]["evidence_items"] == 12
    assert inventory["route_call_caps"] == {
        "CURRENT_CONTEXT": 2,
        "CANONICAL": 3,
        "GRAPH": 3,
        "BOTH": 4,
        "CLARIFICATION": 2,
    }
    assert inventory["stream_contract"]["delta_payload_keys"] == ["text"]
    assert inventory["stream_contract"]["provider_native_token_stream_claimed"] is False
    assert inventory["memory_after_commit"]["default_off_writes"] == 0
    assert inventory["memory_after_commit"]["producer_failure_rolls_back_chat"] is False
    assert inventory["domain_boundary"]["domain_application_framework_imports"] == 0
    router_hotfix = inventory["router_hotfix"]
    assert router_hotfix["diagnostic_version"] == "router-diagnostic.v1"
    assert router_hotfix["durable_namespace"] == (
        "node_state_json.router_diagnostic"
    )
    assert router_hotfix["raw_router_payload_persisted"] is False
    assert router_hotfix["safe_mismatch_explicit_retry"] is True
    assert router_hotfix["automatic_retry"] is False
    assert router_hotfix["failed_before_route_crg_calls"] == 0
    assert router_hotfix["new_schema_migration"] is None
