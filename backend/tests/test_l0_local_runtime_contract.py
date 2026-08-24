from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/check_local_runtime_contract.py"
SPEC = importlib.util.spec_from_file_location("check_local_runtime_contract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
CONTRACT = json.loads(
    (ROOT / "security/local_runtime_contract.json").read_text(encoding="utf-8")
)


def test_repository_runtime_contract_passes() -> None:
    assert CHECKER.check_repo(root=ROOT) == []


def test_contract_rejects_an_extra_host_publication() -> None:
    payload = deepcopy(CONTRACT)
    payload["host_publications"]["backend"] = {
        "address": "127.0.0.1",
        "default_port": 8080,
    }

    assert "only frontend may be published to the host" in CHECKER.validate_contract(
        payload, root=ROOT
    )


def test_contract_rejects_noncanonical_embedded_storage() -> None:
    payload = deepcopy(CONTRACT)
    payload["embedded_storage"]["canonical"] = "postgresql"

    assert "embedded storage contract mismatch" in CHECKER.validate_contract(
        payload, root=ROOT
    )


def test_contract_rejects_incomplete_default_stack() -> None:
    payload = deepcopy(CONTRACT)
    payload["default_services"].append("postgresql")

    assert (
        "default_services must contain the two-service embedded stack"
        in CHECKER.validate_contract(payload, root=ROOT)
    )

def test_contract_rejects_mutable_release_image_identity() -> None:
    payload = deepcopy(CONTRACT)
    payload["release_images"]["backend"]["default_tag"] = "latest"

    assert "release image contract mismatch" in CHECKER.validate_contract(
        payload, root=ROOT
    )


def test_contract_rejects_mutable_supply_chain_tools() -> None:
    payload = deepcopy(CONTRACT)
    payload["supply_chain"]["trivy_image"] = "ghcr.io/aquasecurity/trivy:latest"

    assert "container supply-chain contract mismatch" in CHECKER.validate_contract(
        payload, root=ROOT
    )
