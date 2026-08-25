"""Reject embedded schema drift that bypasses versioned immutable manifests."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SQLITE_SCHEMA = Path("backend/app/runtime/persistence/sqlite_schema.py")
LADYBUG_SCHEMA = Path("backend/app/integrations/ladybug_projection.py")
SQLITE_MANIFESTS = Path("backend/app/runtime/migrations/sqlite_versions/manifests")
LADYBUG_MANIFESTS = Path("backend/app/runtime/migrations/ladybug_versions/manifests")


def _constant(source: str, name: str) -> int:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, int):
            return value
    raise RuntimeError(f"embedded_contract_constant_missing:{name}")


def _git(*arguments: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode != 0:
        raise RuntimeError("embedded_contract_base_unavailable")
    return result.stdout


def _base_text(base_sha: str, path: Path) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{base_sha}:{path.as_posix()}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode == 0:
        return result.stdout
    return None


def _manifest_versions(root: Path) -> tuple[int, ...]:
    versions = []
    for path in root.glob("v*.json"):
        match = re.fullmatch(r"v([1-9][0-9]*)\.json", path.name)
        if match:
            versions.append(int(match.group(1)))
    return tuple(sorted(versions))


def _check_current_inventory() -> list[str]:
    errors: list[str] = []
    sqlite_version = _constant(
        (ROOT / SQLITE_SCHEMA).read_text(encoding="utf-8"),
        "SQLITE_SCHEMA_VERSION",
    )
    ladybug_version = _constant(
        (ROOT / LADYBUG_SCHEMA).read_text(encoding="utf-8"),
        "LADYBUG_PROJECTION_SCHEMA_VERSION",
    )
    for label, version, directory in (
        ("sqlite", sqlite_version, ROOT / SQLITE_MANIFESTS),
        ("ladybug", ladybug_version, ROOT / LADYBUG_MANIFESTS),
    ):
        versions = _manifest_versions(directory)
        if not versions or versions[-1] != version:
            errors.append(
                f"{label}_latest_manifest_mismatch:version={version}:manifests={versions}"
            )
        expected = tuple(range(1, version + 1))
        if versions != expected:
            errors.append(
                f"{label}_manifest_chain_incomplete:expected={expected}:actual={versions}"
            )
    return errors


def _check_base(base_sha: str) -> list[str]:
    errors: list[str] = []
    for label, schema_path, constant_name, manifest_root in (
        ("sqlite", SQLITE_SCHEMA, "SQLITE_SCHEMA_VERSION", SQLITE_MANIFESTS),
        (
            "ladybug",
            LADYBUG_SCHEMA,
            "LADYBUG_PROJECTION_SCHEMA_VERSION",
            LADYBUG_MANIFESTS,
        ),
    ):
        base_source = _base_text(base_sha, schema_path)
        if base_source is None:
            continue
        current_version = _constant(
            (ROOT / schema_path).read_text(encoding="utf-8"),
            constant_name,
        )
        base_version = _constant(base_source, constant_name)
        if current_version < base_version:
            errors.append(
                f"{label}_schema_downgrade_forbidden:base={base_version}:current={current_version}"
            )
        for version in range(1, base_version + 1):
            relative = manifest_root / f"v{version}.json"
            base_manifest = _base_text(base_sha, relative)
            if base_manifest is None:
                # The migration framework can be introduced over an older
                # runtime that had a version constant but no immutable file.
                continue
            current_path = ROOT / relative
            if not current_path.is_file():
                errors.append(f"{label}_manifest_removed:v{version}")
                continue
            if current_path.read_text(encoding="utf-8") != base_manifest:
                errors.append(f"{label}_manifest_mutated:v{version}")
    return errors


def main() -> int:
    errors = _check_current_inventory()
    base_sha = os.environ.get("BASE_SHA", "").strip()
    if base_sha and set(base_sha) != {"0"}:
        errors.extend(_check_base(base_sha))
    if errors:
        for error in errors:
            print(f"embedded-data-migration contract error: {error}", file=sys.stderr)
        return 1
    print(
        "embedded-data-migration contract passed: "
        f"base={base_sha or 'current-only'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
