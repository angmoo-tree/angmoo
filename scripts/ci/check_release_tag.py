"""Verify that an Angmoo release tag matches both application versions."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
import re
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
    versions = {
        "backend": backend_version, "frontend": frontend_version,
        "desktop": json.loads((root / "desktop/package.json").read_text(encoding="utf-8"))["version"],
        "tauri": json.loads((root / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"],
        "cargo": tomllib.loads((root / "desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8"))["package"]["version"],
    }
    desktop_lock = json.loads((root / "desktop/package-lock.json").read_text(encoding="utf-8"))
    versions["desktop-lock"] = desktop_lock["version"]
    versions["desktop-lock-root"] = desktop_lock["packages"][""]["version"]
    for relative, name, key in (("backend/uv.lock", "backend", "uv"), ("desktop/src-tauri/Cargo.lock", "angmoo-desktop", "cargo-lock")):
        packages = tomllib.loads((root / relative).read_text(encoding="utf-8"))["package"]
        matches = [p["version"] for p in packages if p["name"] == name]
        if len(matches) != 1:
            raise ValueError(f"missing or ambiguous self package: {relative}")
        versions[key] = matches[0]
    tree = ast.parse((root / "backend/app/runtime/product_identity.py").read_text(encoding="utf-8"))
    versions["runtime"] = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PRODUCT_VERSION" for t in n.targets))
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", backend_version) or set(versions.values()) != {backend_version}:
        raise ValueError(f"product versions must be identical: {versions}")
    return f"release-v{backend_version}"


def validate_release_tag(tag: str, root: Path = ROOT) -> list[str]:
    try:
        expected = expected_release_tag(root)
    except (OSError, ValueError, KeyError, StopIteration) as exc:
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
