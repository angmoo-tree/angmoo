"""Collect the current corpus and execute its verified full/scoped partition."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

import pytest

from backend_shard_contract import ExecutionCoverage
from impact import read_plan

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--impact-plan", type=Path)
    args = parser.parse_args()
    if Path.cwd().resolve() != (ROOT / "backend").resolve():
        raise ValueError("backend_shard_requires_backend_working_directory")
    # Match `python -m pytest`: a script launch otherwise places scripts/ci,
    # rather than the verified backend working directory, on sys.path.
    sys.path.insert(0, str(ROOT / "backend"))
    if re.fullmatch(r"[0-9a-f]{40}", args.source_sha) is None:
        raise ValueError("backend_shard_source_invalid")
    git = lambda *values: subprocess.check_output(["git", *values], cwd=ROOT, text=True).strip()
    subprocess.run(["git", "merge-base", "--is-ancestor", args.source_sha, "HEAD"], cwd=ROOT, check=True)
    identity = {"source_sha": args.source_sha, "checkout_sha": git("rev-parse", "HEAD"),
        "checkout_tree": git("rev-parse", "HEAD^{tree}"), "python": platform.python_version(),
        "lock_sha256": hashlib.sha256((ROOT / "backend/uv.lock").read_bytes()).hexdigest(),
        "run_id": os.environ.get("GITHUB_RUN_ID", "0"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1")}
    output = ROOT / "backend/.ci"
    output.mkdir(exist_ok=True)
    journal = output / "backend-shard-events.jsonl"
    journal.write_text("", encoding="utf-8")
    selection = read_plan(args.impact_plan)["effective"] if args.impact_plan else None
    if os.environ.get("GITHUB_ACTIONS") == "true" and selection is None:
        raise ValueError("backend_hosted_impact_plan_required")
    coverage = ExecutionCoverage(args.index, journal, selection)
    (output / "backend-test-identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    # Selection comes exclusively from the verified plan and whole `tests`
    # collection. No -k/-m/ignore/maxfail or caller-supplied pytest flags exist.
    code = int(pytest.main(["-vv", "--tb=short", "tests", "--durations=25",
        f"--junitxml={output / 'backend-junit.xml'}"], plugins=[coverage]))
    if code == 5 and coverage.collection_completed and coverage.suite_nodes and not coverage.selected:
        code = 0  # Proven empty partition of a nonempty scoped suite.
    report = output / "backend-shard-report.json"
    pending = report.with_suffix(".tmp")
    pending.write_text(json.dumps(coverage.report(identity, code), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
