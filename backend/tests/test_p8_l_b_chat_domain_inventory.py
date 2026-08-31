from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
A_INVENTORY_SHA256 = "934c1410810e8f0b0899e09c3c34b5c67f43050c4a354a15fcea72f264c9847e"
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _sha256(relative: str) -> str:
    data = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def test_p8_l_b_generated_inventory_is_current() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ci/generate_p8_l_b_chat_domain_inventory.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_b_is_append_only_from_the_frozen_a_inventory() -> None:
    inventory = _json("security/p8_l_b_chat_domain_inventory.json")
    assert _sha256("security/p8_l_a_inventory.json") == A_INVENTORY_SHA256
    assert inventory["predecessor"]["sha256"] == A_INVENTORY_SHA256
    assert inventory["owner_stage"] == "P8-L-B"
    assert inventory["architecture"]["removed_frozen_legacy_edge_count"] == 10
    assert inventory["architecture"]["remaining_frozen_legacy_edges"] == []
    assert inventory["architecture"]["pure_layer_violations"] == []


def test_p8_l_b_preserves_v1_transport_storage_and_call_contracts() -> None:
    inventory = _json("security/p8_l_b_chat_domain_inventory.json")
    policy = _json("security/p8_l_b_chat_domain_policy.json")
    assert inventory["route_operations"] == policy["required_route_operations"]
    assert len(inventory["route_operations"]) == 11
    assert inventory["tables"] == policy["required_tables"]
    assert len(inventory["tables"]) == 4
    assert [item["path"] for item in inventory["message_migrations"]] == policy[
        "required_message_migrations"
    ]
    assert inventory["migration_baseline"] == {
        "alembic": {"heads": ["20260825_0083"], "revision_count": 82},
        "embedded_sqlite": {
            "canonical_table_count": 87,
            "schema_digest": "e8f4567a32efb3250a9c6f8d36bd6ae604364f3196e039922555ead6e6ec42aa",
            "schema_version": 3,
            "source_migration_count": 82,
            "source_revision": "20260825_0083",
        },
    }
    assert inventory["service_contract"] == policy["service_contract"]


def test_p8_l_b_compatibility_facades_preserve_object_identity() -> None:
    legacy_models = importlib.import_module("app.models.messages")
    canonical_models = importlib.import_module(
        "app.domains.chat.infrastructure.sqlalchemy_models"
    )
    legacy_schemas = importlib.import_module("app.schemas.messages")
    canonical_schemas = importlib.import_module("app.domains.chat.api.schemas")
    community_schemas = importlib.import_module("app.schemas.community")
    core_profile_ref = importlib.import_module("app.core.profile_ref")
    policy = _json("security/p8_l_b_chat_domain_policy.json")

    for name in policy["compatibility_exports"]["models"]:
        assert getattr(legacy_models, name) is getattr(canonical_models, name)
    for name in policy["compatibility_exports"]["schemas"]:
        assert getattr(legacy_schemas, name) is getattr(canonical_schemas, name)
    assert canonical_schemas.ProfileRef is core_profile_ref.ProfileRef
    assert community_schemas.ProfileRef is core_profile_ref.ProfileRef
    profile_schema = core_profile_ref.ProfileRef.model_json_schema()
    profile_contract = policy["profile_ref_contract"]
    assert list(profile_schema["properties"]) == profile_contract["fields"]
    assert profile_schema["required"] == profile_contract["required_fields"]
    assert profile_schema["properties"]["profile_type"]["enum"] == profile_contract[
        "profile_types"
    ]

    legacy_service = importlib.import_module("app.services.messages")
    canonical_service = importlib.import_module("app.runtime.chat.sqlalchemy_service")
    assert legacy_service is canonical_service
    legacy_prompt_safety = importlib.import_module("app.services.prompt_safety")
    canonical_prompt_safety = importlib.import_module("app.core.prompt_safety")
    assert legacy_prompt_safety is canonical_prompt_safety
