"""Audit locked dependency licenses and render a deterministic notice."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_NODE_PREFIXES = (
    "@img/sharp-",
    "@next/swc-",
)
PLATFORM_PYTHON_LICENSE_FALLBACKS = {
    "colorama": "OSI Approved :: BSD License",
    "tzdata": "Apache-2.0",
}
FORBIDDEN_LICENSE = re.compile(r"AGPL|SSPL|(?<!L)GPL", re.IGNORECASE)


class LicenseAuditError(RuntimeError):
    pass


def _normalized_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _metadata_license(metadata: importlib.metadata.PackageMetadata) -> str:
    expression = (metadata.get("License-Expression") or metadata.get("License") or "").strip()
    if expression and expression.lower() not in {"unknown", "none"}:
        return " ".join(expression.split())
    classifiers = sorted(
        {
            value.removeprefix("License :: ").strip()
            for value in metadata.get_all("Classifier", [])
            if value.startswith("License :: ")
        }
    )
    return " OR ".join(classifiers)


def python_inventory(repo_root: Path) -> list[tuple[str, str, str]]:
    lock_path = repo_root / "backend" / "uv.lock"
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    locked = {
        _normalized_name(item["name"]): str(item["version"])
        for item in lock["package"]
        if _normalized_name(item["name"]) != "backend"
    }
    installed: dict[str, tuple[str, str, str]] = {}
    for distribution in importlib.metadata.distributions():
        name = _normalized_name(distribution.metadata.get("Name") or "")
        if name not in locked:
            continue
        installed[name] = (
            name,
            distribution.version,
            _metadata_license(distribution.metadata),
        )
    missing = sorted(set(locked) - set(installed))
    unsupported_missing = [
        name for name in missing if name not in PLATFORM_PYTHON_LICENSE_FALLBACKS
    ]
    if unsupported_missing:
        raise LicenseAuditError(
            "locked Python packages are not installed: "
            + ", ".join(unsupported_missing)
        )
    for name in missing:
        installed[name] = (
            name,
            locked[name],
            PLATFORM_PYTHON_LICENSE_FALLBACKS[name],
        )
    return sorted(installed.values())


def node_inventory(repo_root: Path) -> list[tuple[str, str, str]]:
    result = subprocess.run(
        ["pnpm.cmd" if os.name == "nt" else "pnpm", "licenses", "list", "--prod", "--json"],
        cwd=repo_root / "frontend",
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise LicenseAuditError(result.stderr.strip() or "pnpm license inventory failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LicenseAuditError("pnpm returned invalid license JSON") from exc

    packages: set[tuple[str, str, str]] = set()
    for license_name, entries in payload.items():
        normalized_license = " ".join(str(license_name).split())
        for entry in entries:
            name = str(entry["name"])
            if name.startswith(PLATFORM_NODE_PREFIXES):
                continue
            for version in entry.get("versions", []):
                packages.add((name, str(version), normalized_license))
    return sorted(packages, key=lambda row: (row[0].lower(), row[1], row[2]))


def _validate_inventory(
    ecosystem: str, packages: list[tuple[str, str, str]]
) -> None:
    if not packages:
        raise LicenseAuditError(f"{ecosystem} dependency inventory is empty")
    invalid = [
        f"{name}@{version} ({license_name or 'unknown'})"
        for name, version, license_name in packages
        if not license_name or FORBIDDEN_LICENSE.search(license_name)
    ]
    if invalid:
        raise LicenseAuditError(
            f"{ecosystem} has unknown or disallowed licenses: " + ", ".join(invalid)
        )


def render_notice(
    python_packages: list[tuple[str, str, str]],
    node_packages: list[tuple[str, str, str]],
) -> str:
    lines = [
        "# Third-party notices",
        "",
        "This inventory is generated from the locked Angmoo dependencies.",
        "Package authors retain all rights granted by their respective licenses.",
        "",
        f"## Python packages ({len(python_packages)})",
        "",
    ]
    lines.extend(
        f"- `{name} {version}` — {license_name}"
        for name, version, license_name in python_packages
    )
    lines.extend(
        [
            "",
            f"## JavaScript production packages ({len(node_packages)})",
            "",
        ]
    )
    lines.extend(
        f"- `{name} {version}` — {license_name}"
        for name, version, license_name in node_packages
    )
    lines.extend(
        [
            "",
            "This notice does not replace license text distributed by an individual dependency.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--write-notice", type=Path)
    parser.add_argument("--check-notice", type=Path)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    try:
        python_packages = python_inventory(repo_root)
        node_packages = node_inventory(repo_root)
        _validate_inventory("Python", python_packages)
        _validate_inventory("JavaScript", node_packages)
        notice = render_notice(python_packages, node_packages)
        if args.write_notice is not None:
            args.write_notice.resolve().write_text(
                notice, encoding="utf-8", newline="\n"
            )
        if args.check_notice is not None:
            current = args.check_notice.resolve().read_text(encoding="utf-8")
            if current != notice:
                raise LicenseAuditError("third-party notice does not match locked dependencies")
    except (OSError, LicenseAuditError) as exc:
        print(f"Dependency license audit failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Dependency license audit passed: "
        f"python={len(python_packages)} node={len(node_packages)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
