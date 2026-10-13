"""Reject any missing, failed, mismatched or unexecuted backend CI partition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import os

from backend_shard_contract import verify_reports
from impact import read_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--impact-plan", type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    paths = sorted(root.rglob("backend-shard-report.json"))
    if any(path.is_symlink() or not path.resolve().is_relative_to(root) for path in paths):
        raise ValueError("backend_shard_report_path_invalid")
    plan = read_plan(args.impact_plan)
    result = verify_reports([json.loads(path.read_text(encoding="utf-8")) for path in paths],
        source_sha=args.source_sha, checkout_sha=args.checkout_sha, checkout_tree=plan["checkout_tree"], selection=plan["effective"],
        run_id=os.environ.get("GITHUB_RUN_ID", "0"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    print(json.dumps(result, sort_keys=True))
    (root / "backend-shard-coverage.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
