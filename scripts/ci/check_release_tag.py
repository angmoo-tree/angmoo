"""Verify that an Angmoo release tag matches both application versions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def expected_release_tag(root: Path = ROOT) -> str:
    backend = tomllib.loads(
        (root / "backend/pyproject.toml").read_text(encoding="utf-8")
    )
    frontend = json.loads(
        (root / "frontend/package.json").read_text(encoding="utf-8")
    )
    backend_version = str(backend.get("project", {}).get("version", ""))
    frontend_version = str(frontend.get("version", ""))
    if not backend_version or backend_version != frontend_version:
        raise ValueError(
            "backend and frontend release versions must be present and identical"
        )
    return f"v{backend_version}"


def validate_release_tag(tag: str, root: Path = ROOT) -> list[str]:
    try:
        expected = expected_release_tag(root)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        return [f"release version cannot be resolved: {exc}"]
    if tag != expected:
        return [f"release tag mismatch: tag={tag!r} expected={expected!r}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    errors = validate_release_tag(args.tag, args.repo_root.resolve())
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"Release tag passed: {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
