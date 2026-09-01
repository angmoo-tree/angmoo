from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
D_INVENTORY_SHA256 = "f0f5c1e1b9bf5ddcbf86f30ccc812ce30597f1a16ca08dd61040eb9610a322a3"


def _sha256(relative: str) -> str:
    data = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _inventory() -> dict:
    return json.loads(
        (
            ROOT
            / "docs/architecture/p8-l-e-world-social-chat-entry-inventory.json"
        ).read_text(encoding="utf-8")
    )


def test_p8_l_e_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_e_world_social_chat_entry_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_e_chains_frozen_d_without_rewriting_history() -> None:
    inventory = _inventory()
    assert (
        _sha256("docs/architecture/p8-l-d-world-chat-identity-inventory.json")
        == D_INVENTORY_SHA256
    )
    assert inventory["owner_stage"] == "P8-L-E"
    assert inventory["predecessor"]["sha256"] == D_INVENTORY_SHA256
    assert inventory["historical_chain"] == {
        "current_tree_owner": "P8-L-E",
        "p8_l_d_sha256": D_INVENTORY_SHA256,
        "predecessor_mode": "frozen_digest",
    }


def test_p8_l_e_inventory_closes_routes_capabilities_and_non_scope() -> None:
    inventory = _inventory()
    assert inventory["backend"]["requester_cardinality"] == [
        "zero",
        "one",
        "anomaly",
    ]
    assert inventory["backend"]["create_or_get_operation"] == (
        "POST /worlds/{world_id}/chat/threads"
    )
    assert inventory["frontend"]["profile_route"] == (
        "/worlds/{worldId}/characters/{worldCharacterId}"
    )
    assert inventory["frontend"]["route_parity"] == ["next", "static", "tauri"]
    assert inventory["non_scope"] == [
        "message_send",
        "response_generation",
        "streaming",
        "retrieval",
        "memory_write",
    ]
