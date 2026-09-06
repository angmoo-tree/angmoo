"""Keep the frozen parity count and validate every current source entry."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = "d7037625a19071eb279ad2ea35c3ace6fe5b5289"


def frozen_checkpoint_behavior() -> dict:
    return json.loads(subprocess.check_output(
        ["git", "show", f"{CHECKPOINT}:security/l4_pr_a_inventory.json"],
        cwd=ROOT,
    ))["behavior"]


def assert_live_parity_matches_source(behavior: dict) -> None:
    policy = json.loads((ROOT / "security/l4_pr_a_inventory_policy.json").read_text(encoding="utf-8"))
    moves = json.loads((ROOT / "security/refactor_path_map.json").read_text(encoding="utf-8"))
    expected_nodes = []
    expected_files = []
    for relative in policy["parity_test_files"]:
        content = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        expected_files.append({"path": relative, "sha256": hashlib.sha256(content).hexdigest()})
        tree = ast.parse(content.decode("utf-8-sig"), filename=relative)
        expected_nodes.extend(
            f"{relative}::{node.name}"
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    expected_nodes.sort()
    assert behavior["parity_test_files"] == expected_files
    assert behavior["parity_test_nodes"] == expected_nodes
    assert behavior["parity_test_node_count"] == len(expected_nodes)

    def moved_node(original: str) -> str:
        node = original.removeprefix("backend/")
        seen = set()
        while node in moves["test_nodes"]:
            assert node not in seen
            seen.add(node)
            node = moves["test_nodes"][node]
        path, function = ("backend/" + node).split("::", 1)
        seen.clear()
        while path in moves["files"]:
            assert path not in seen
            seen.add(path)
            path = moves["files"][path]
        return f"{path}::{function}"

    frozen = frozen_checkpoint_behavior()
    assert {moved_node(node) for node in frozen["parity_test_nodes"]} <= set(expected_nodes)
    expected_counters = [
        {**item, "test": moved_node(item["test"])}
        for item in frozen["counter_contracts"]
    ]
    assert behavior["counter_contracts"] == expected_counters
    assert policy["behavior_counters"] == expected_counters
    assert all(item["test"] in expected_nodes for item in expected_counters)


@pytest.mark.parametrize("mutation", ["count", "missing_node", "counter"])
def test_live_parity_rejects_stale_or_changed_evidence(mutation: str) -> None:
    from test_l4_pr_a_inventory import generator

    behavior = copy.deepcopy(generator.build_inventory()["behavior"])
    if mutation == "count":
        behavior["parity_test_node_count"] -= 1
    elif mutation == "missing_node":
        behavior["parity_test_nodes"].pop()
        behavior["parity_test_node_count"] -= 1
    else:
        behavior["counter_contracts"][0]["expected"] += 1
    with pytest.raises(AssertionError):
        assert_live_parity_matches_source(behavior)
