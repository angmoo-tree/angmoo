"""Reject unsafe or unpinned GitHub Actions workflow configuration."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


ACTION = re.compile(r"(?m)^\s*-\s+uses:\s+([^\s#]+)")
FULL_SHA = re.compile(r"^[^@]+@[0-9a-f]{40}$")
FORBIDDEN = {
    "pull_request_target": "pull_request_target event",
    "self-hosted": "self-hosted runner",
    "${{ secrets.": "repository secret reference",
    "actions/upload-artifact@": "raw artifact upload",
    "permissions: write": "write permission",
}
REQUIRED_JOBS = {
    "backend-contract",
    "frontend",
    "quickstart",
    "security-export",
    "dependency-audit",
}


def check(workflow: Path) -> list[str]:
    text = workflow.read_text(encoding="utf-8")
    errors = [
        f"forbidden workflow feature: {label}"
        for marker, label in FORBIDDEN.items()
        if marker in text
    ]
    actions = ACTION.findall(text)
    errors.extend(
        f"action is not pinned to a full commit SHA: {action}"
        for action in actions
        if not action.startswith("./") and not FULL_SHA.fullmatch(action)
    )
    if "permissions:\n  contents: read\n" not in text:
        errors.append("top-level permissions must be contents: read")
    missing_jobs = sorted(
        job for job in REQUIRED_JOBS if not re.search(rf"(?m)^  {re.escape(job)}:\s*$", text)
    )
    errors.extend(f"required job is missing: {job}" for job in missing_jobs)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflow", type=Path, default=Path(".github/workflows/ci.yml")
    )
    args = parser.parse_args()
    try:
        errors = check(args.workflow)
    except OSError as exc:
        print(f"CI policy check failed: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("CI policy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
