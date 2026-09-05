from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO_ROOT / "scripts/ci/generate_l4_pr_a_inventory.py"
SPEC = importlib.util.spec_from_file_location(
    "angmoo_l4_pr_a_inventory", GENERATOR_PATH
)
assert SPEC is not None and SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


def frozen_checkpoint_backend_architecture() -> dict:
    """Keep the pre-refactor topology numbers tied to their immutable commit."""
    source = subprocess.check_output(
        [
            "git", "show",
            "d7037625a19071eb279ad2ea35c3ace6fe5b5289:security/l4_pr_a_inventory.json",
        ],
        cwd=REPO_ROOT,
    )
    return json.loads(source)["architecture"]["backend"]


def assert_live_backend_matches_source(backend: dict) -> None:
    """Compare the live L4 report with source analysis, not its cached totals."""
    source_spec = importlib.util.spec_from_file_location(
        "angmoo_l4_current_source_inventory",
        REPO_ROOT / "scripts/ci/generate_architecture_inventory.py",
    )
    assert source_spec is not None and source_spec.loader is not None
    source_generator = importlib.util.module_from_spec(source_spec)
    source_spec.loader.exec_module(source_generator)
    source = source_generator.build_inventory(root=REPO_ROOT)
    assert backend["module_count"] == source["module_count"]
    assert backend["internal_edge_count"] == source["edge_count"]
    assert backend["external_import_count"] == source["external_import_count"]
    assert backend["legacy_import_exception_count"] == 0
    assert backend["policy_allowed_cycle_count"] == 0
    assert backend["module_cycles"] == []
    policy = json.loads(generator.DEFAULT_POLICY.read_text(encoding="utf-8"))
    assert set(backend["ownership"]) == set(policy["backend_ownership"])
    for owner, prefixes in policy["backend_ownership"].items():
        expected = {
            item["module"]: (item["path"], item["imports"])
            for item in source["modules"]
            if any(item["module"] == prefix or item["module"].startswith(prefix + ".") for prefix in prefixes)
        }
        observed = {
            item["module"]: (item["path"], item["imports"])
            for item in backend["ownership"][owner]
        }
        assert observed == expected
        assert len(backend["ownership"][owner]) == len(expected)


def test_l4_pr_a_inventory_is_deterministic_and_current() -> None:
    first = generator.render()
    second = generator.render()
    payload = json.loads(first)

    assert first == second
    assert generator.DEFAULT_OUTPUT.read_text(encoding="utf-8") == first
    assert payload["schema_version"] == 1
    assert payload["policy_id"] == "angmoo-l4-pr-a-p5-p7-inventory-v1"
    assert payload["baseline_commit"] == ("0917bfa6bbb14c4b15a4a26d1f221817bd4e52e1")


def test_l4_pr_a_text_hash_is_stable_across_checkout_line_endings(
    tmp_path: Path,
) -> None:
    lf_path = tmp_path / "lf.txt"
    crlf_path = tmp_path / "crlf.txt"
    lf_path.write_bytes(b"first\nsecond\n")
    crlf_path.write_bytes(b"first\r\nsecond\r\n")

    assert generator._sha256(lf_path) == generator._sha256(crlf_path)


def test_l4_pr_a_runtime_and_installer_baselines_are_frozen() -> None:
    payload = generator.build_inventory()
    sqlite = payload["runtime"]["sqlite"]
    ladybug = payload["runtime"]["ladybug"]

    assert [item["contract"]["schema_version"] for item in sqlite["manifests"]] == [
        1,
        2,
        3,
    ]
    assert [
        item["contract"]["canonical_table_count"] for item in sqlite["manifests"]
    ] == [83, 87, 87]
    assert len(sqlite["steps"]) == 2
    assert [
        item["contract"]["projection_schema_version"]
        for item in ladybug["manifests"]
    ] == [1, 2]
    assert ladybug["manifests"][1]["contract"] == {
        "minimum_ladybug_version": "0.19.1",
        "parity_contract_version": 1,
        "projection_schema_version": 2,
        "schema_digest": "a028adfa2162e4cec41a4d8efd58731b696185742632c37beac3e8fb13f099f4",
    }
    assert payload["installer"]["required_jobs"] == [
        "release-candidate",
        "windows-installer-supported-upgrade",
        "windows-installer-failure-recovery",
        "installed-runtime-smoke",
        "windows-installer",
    ]


def test_l4_pr_a_architecture_and_parity_oracles_are_exact() -> None:
    payload = generator.build_inventory()
    # File/edge totals intentionally change during an architecture migration.
    # Preserve the original checkpoint assertions and validate the current
    # report separately against actual source; runtime/parity remain live.
    backend = frozen_checkpoint_backend_architecture()
    frontend = payload["architecture"]["frontend"]
    behavior = payload["behavior"]

    assert_live_backend_matches_source(payload["architecture"]["backend"])

    assert backend["module_count"] == 680
    assert backend["internal_edge_count"] == 1837
    assert backend["external_import_count"] == 2288
    assert backend["legacy_import_exception_count"] == 0
    assert backend["policy_allowed_cycle_count"] == 0
    assert backend["module_cycles"] == []
    assert len(backend["ownership"]["legacy_horizontal"]) == 8
    assert len(backend["ownership"]["canonical_boundaries"]) == 74

    assert frontend["candidate_count"] == 14
    assert frontend["candidate_consumer_edge_count"] == 27
    assert frontend["planned_feature_allowlist"] == ["relationships", "social"]
    assert len(frontend["public_surfaces"]["features"]) == 13
    assert len(frontend["public_surfaces"]["shared"]) == 8

    assert behavior["parity_test_node_count"] == 97
    nodes = set(behavior["parity_test_nodes"])
    assert all(item["test"] in nodes for item in behavior["counter_contracts"])
    assert payload["forbidden_changes"] == [
        "schema",
        "endpoint",
        "relationship_delta",
        "provider_call_count",
        "production_composition",
    ]


@pytest.mark.parametrize("field", ["module_count", "internal_edge_count", "external_import_count"])
def test_live_l4_architecture_rejects_stale_source_totals(field: str) -> None:
    backend = generator.build_inventory()["architecture"]["backend"]
    backend[field] += 1
    with pytest.raises(AssertionError):
        assert_live_backend_matches_source(backend)
