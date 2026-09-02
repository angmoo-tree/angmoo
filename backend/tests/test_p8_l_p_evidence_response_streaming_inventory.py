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
        "3fe3a33e970c0d50b915e93f9cfd1f4d2f78288b54d17ec2dce48aa0e2422f40"
    )
    assert inventory["schema"]["current_embedded_schema_version"] == 6
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
