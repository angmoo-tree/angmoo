"""Prove complete execution of the original backend corpus across isolated jobs."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from impact import digest as selection_digest, select_nodes

SHARD_COUNT = 4
SCHEMA = "backend-test-shard.v2"


def shard_for(node: str) -> int:
    return int.from_bytes(hashlib.sha256(node.encode("utf-8")).digest()[:8], "big") % SHARD_COUNT


def collection_digest(nodes: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(nodes), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def node_result(phases: dict[str, str]) -> str:
    if (not isinstance(phases, dict) or set(phases) - {"setup", "call", "teardown"}
            or any(value not in {"passed", "failed", "skipped"} for value in phases.values())):
        return "incomplete"
    if "failed" in phases.values():
        return "failed"
    if phases.get("teardown") != "passed":
        return "incomplete"
    if phases.get("setup") == "skipped":
        return "skipped"
    if phases.get("setup") != "passed":
        return "incomplete"
    if phases.get("call") in {"passed", "skipped"}:
        return phases["call"]
    return "incomplete"


class ExecutionCoverage:
    def __init__(self, index: int, journal: Path, selection: dict | None = None):
        if type(index) is not int or not 0 <= index < SHARD_COUNT:
            raise ValueError("invalid_backend_shard_index")
        self.index = index
        self.journal = journal
        self.all_nodes: list[str] = []
        self.selected: list[str] = []
        self.phases: dict[str, dict[str, str]] = defaultdict(dict)
        self.collection_completed = False
        self.selection = selection or {"backend": "full", "test_paths": []}
        self.suite_nodes: list[str] = []

    def pytest_collection_modifyitems(self, config, items):
        import pytest

        self.all_nodes = [item.nodeid for item in items]
        if not self.all_nodes or len(self.all_nodes) != len(set(self.all_nodes)):
            raise pytest.UsageError("backend_collection_empty_or_duplicate")
        self.suite_nodes = select_nodes(self.all_nodes, self.selection)
        selected, deselected = [], []
        for item in items:
            (selected if item.nodeid in self.suite_nodes and shard_for(item.nodeid) == self.index else deselected).append(item)
        if not selected and self.selection["backend"] == "full":
            raise pytest.UsageError("backend_shard_empty")
        self.selected = [item.nodeid for item in selected]
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
        self.collection_completed = True

    def pytest_runtest_logreport(self, report):
        if report.nodeid not in self.selected or report.when not in {"setup", "call", "teardown"}:
            raise RuntimeError("backend_shard_unselected_report")
        if report.when in self.phases[report.nodeid]:
            raise RuntimeError("backend_shard_duplicate_phase")
        self.phases[report.nodeid][report.when] = report.outcome
        # Durable progress survives interruption. It is diagnostic, never a PASS.
        with self.journal.open("a", encoding="utf-8") as output:
            output.write(json.dumps({"node": report.nodeid, "phase": report.when,
                "outcome": report.outcome, "seconds": report.duration}, ensure_ascii=False) + "\n")

    def report(self, identity: dict, exit_code: int) -> dict:
        return {"schema": SCHEMA, "identity": identity, "index": self.index,
            "count": SHARD_COUNT, "collection_completed": self.collection_completed,
            "all_nodes": self.all_nodes, "collection_sha256": collection_digest(self.all_nodes),
            "suite_nodes": self.suite_nodes, "suite_sha256": collection_digest(self.suite_nodes),
            "selection_sha256": selection_digest(self.selection),
            "selected_nodes": self.selected, "exit_code": exit_code,
            "results": {node: {"phases": self.phases[node], "outcome": node_result(self.phases[node])}
                        for node in self.selected}}


def verify_reports(reports: list[dict], *, source_sha: str, checkout_sha: str,
                   selection: dict | None = None, run_id: str = "0", run_attempt: str = "1") -> dict:
    selection = selection or {"backend": "full", "test_paths": []}
    if any(re.fullmatch(r"[0-9a-f]{40}", value) is None for value in (source_sha, checkout_sha)):
        raise ValueError("backend_coverage_commit_invalid")
    if len(reports) != SHARD_COUNT:
        raise ValueError("backend_shard_reports_missing")
    if {report.get("index") for report in reports} != set(range(SHARD_COUNT)):
        raise ValueError("backend_shard_indices_invalid")
    reference = reports[0].get("all_nodes")
    if not isinstance(reference, list) or not reference or any(not isinstance(node, str) for node in reference):
        raise ValueError("backend_collection_invalid")
    if len(reference) != len(set(reference)):
        raise ValueError("backend_collection_duplicate")
    digest = collection_digest(reference)
    suite = select_nodes(reference, selection)
    identities = []
    executed: list[str] = []
    totals = {"passed": 0, "skipped": 0}
    for report in reports:
        index = report["index"]
        if (type(index) is not int or report.get("schema") != SCHEMA or report.get("count") != SHARD_COUNT
                or report.get("collection_completed") is not True
                or type(report.get("exit_code")) is not int or report.get("exit_code") != 0):
            raise ValueError("backend_shard_not_completed_successfully")
        identity = report.get("identity", {})
        if (not isinstance(identity, dict) or set(identity) != {
                "source_sha", "checkout_sha", "checkout_tree", "python", "lock_sha256", "run_id", "run_attempt"}
                or re.fullmatch(r"[0-9a-f]{40}", identity.get("checkout_tree", "")) is None
                or re.fullmatch(r"[0-9a-f]{64}", identity.get("lock_sha256", "")) is None
                or re.fullmatch(r"\d+\.\d+\.\d+", identity.get("python", "")) is None):
            raise ValueError("backend_shard_runtime_identity_invalid")
        if identity.get("source_sha") != source_sha or identity.get("checkout_sha") != checkout_sha:
            raise ValueError("backend_shard_source_mismatch")
        if identity.get("run_id") != run_id or identity.get("run_attempt") != run_attempt:
            raise ValueError("backend_shard_run_mismatch")
        identities.append(identity)
        if (report.get("all_nodes") != reference or report.get("collection_sha256") != digest):
            raise ValueError("backend_shard_collection_mismatch")
        if (report.get("suite_nodes") != suite or report.get("suite_sha256") != collection_digest(suite)
                or report.get("selection_sha256") != selection_digest(selection)):
            raise ValueError("backend_shard_suite_mismatch")
        expected = [node for node in suite if shard_for(node) == index]
        if (not expected and selection["backend"] == "full") or report.get("selected_nodes") != expected:
            raise ValueError("backend_shard_selection_mismatch")
        results = report.get("results")
        if not isinstance(results, dict) or set(results) != set(expected):
            raise ValueError("backend_shard_results_missing")
        for node in expected:
            result = results[node]
            outcome = node_result(result.get("phases", {}))
            if outcome not in totals or result.get("outcome") != outcome:
                raise ValueError("backend_shard_test_failed_or_incomplete")
            totals[outcome] += 1
        executed.extend(expected)
    if any(identity != identities[0] for identity in identities[1:]):
        raise ValueError("backend_shard_runtime_identity_mismatch")
    if not executed or len(executed) != len(set(executed)) or set(executed) != set(suite):
        raise ValueError("backend_shard_union_incomplete")
    return {"schema": "backend-test-coverage.v2", "source_sha": source_sha,
        "checkout_sha": checkout_sha, "collection_sha256": digest,
        "profile": selection["backend"], "suite_sha256": collection_digest(suite),
        "run_id": run_id, "run_attempt": run_attempt,
        "collected": len(reference), "selected": len(suite), "covered": len(executed), "shards": SHARD_COUNT, **totals}
