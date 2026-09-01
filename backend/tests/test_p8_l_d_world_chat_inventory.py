from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
A_INVENTORY_SHA256 = "934c1410810e8f0b0899e09c3c34b5c67f43050c4a354a15fcea72f264c9847e"
B_INVENTORY_SHA256 = "d9e5b83d78059d91629f001e48d3031bd44a495f625be1588f00770395c5d70e"


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _sha256(relative: str) -> str:
    data = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def test_p8_l_d_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_d_world_chat_inventory.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_d_chains_frozen_a_and_b_without_rewriting_history() -> None:
    inventory = _json(
        "docs/architecture/p8-l-d-world-chat-identity-inventory.json"
    )
    assert _sha256("security/p8_l_a_inventory.json") == A_INVENTORY_SHA256
    assert _sha256("security/p8_l_b_chat_domain_inventory.json") == B_INVENTORY_SHA256
    assert inventory["owner_stage"] == "P8-L-D"
    assert inventory["predecessor"]["sha256"] == B_INVENTORY_SHA256
    assert inventory["historical_chain"] == {
        "current_tree_owner": "P8-L-D",
        "p8_l_a_sha256": A_INVENTORY_SHA256,
        "p8_l_b_sha256": B_INVENTORY_SHA256,
        "predecessor_mode": "frozen_digest",
    }
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate_p8_l_b_chat_domain_inventory.py",
            "--write",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 1
    assert "P8-L-B inventory is frozen" in result.stderr
    assert _sha256("security/p8_l_b_chat_domain_inventory.json") == B_INVENTORY_SHA256


def test_p8_l_d_freezes_world_chat_v4_migration_and_transport_contract() -> None:
    inventory = _json(
        "docs/architecture/p8-l-d-world-chat-identity-inventory.json"
    )
    assert inventory["migration"] == {
        "alembic_down_revision": "20260825_0083",
        "alembic_revision": "20260831_0084",
        "embedded_sqlite": {
            "canonical_table_count": 87,
            "schema_digest": "520b6dfafdae9fc26b11a40ff147eef4596122cde3a40559a2cd4fc1a3ea875c",
            "schema_version": 4,
            "source_migration_count": 83,
            "source_revision": "20260831_0084",
        },
        "migration_registry_step": "v3_to_v4_world_scoped_chat",
        "mutable_identity_tables": ["message_threads"],
    }
    assert inventory["message_thread"]["backfill_outcomes"] == [
        "resolved",
        "ambiguous",
        "quarantined",
    ]
    assert inventory["message_thread"]["legacy_columns_preserved"] is True
    assert inventory["message_thread"]["lossless_messages_required"] is True
    assert inventory["transport"]["route_operations"] == [
        "GET /worlds/{world_id}/chat/threads",
        "GET /worlds/{world_id}/chat/threads/{thread_id}",
        "POST /worlds/{world_id}/chat/threads",
    ]


def test_p8_l_d_requires_real_v3_installer_fixture_in_hosted_matrix() -> None:
    inventory = _json(
        "docs/architecture/p8-l-d-world-chat-identity-inventory.json"
    )
    assert inventory["installer_upgrade"] == {
        "hosted_workflow_archive": "supported-v3.zip",
        "idempotent_target_reinstall_verified": True,
        "message_survival_verified": True,
        "required_predecessor": 3,
        "supported_predecessor_present": True,
        "synthetic_fixture_has_resolved_and_ambiguous_threads": True,
    }
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/check_windows_installer_supported_upgrade_matrix.py",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("v1,v2,v3,v4,v5")
