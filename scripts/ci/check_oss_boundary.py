"""Reject obsolete two-repository CI paths and stale contributor instructions."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_TRACKED_PATHS = {
    "scripts/classify_hosted_impact.py",
    "security/hosted_impact_policy.json",
    "backend/tests/test_phase4_hosted_impact.py",
    "scripts/build_public_candidate.py",
    "security/public_export_policy.json",
    "backend/tests/test_m4_public_export.py",
}
ACTIVE_SURFACES = {
    "CONTRIBUTING.md",
    "CONTRIBUTING.ko.md",
    "docs/public/contribution-map.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/feature.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
}
STALE_MARKERS = {
    "hosted-impact",
    "backend-contract",
    "security-export",
    "dependency-audit",
    "requires-hosted-validation",
    "jingujeon/angmoo/security/advisories/new",
    "Private integration",
    "private integration",
}
REQUIRED_MARKERS = {
    "CONTRIBUTING.md": ("angmoo-tree/angmoo", "required approvals: 0", "git commit -s"),
    "CONTRIBUTING.ko.md": ("angmoo-tree/angmoo", "required approvals: 0", "git commit -s"),
    "docs/public/contribution-map.md": ("angmoo-tree/angmoo", "required checks"),
    ".github/PULL_REQUEST_TEMPLATE.md": ("Local OSS", "DCO 1.1", "GPL-3.0-only"),
    ".github/ISSUE_TEMPLATE/config.yml": (
        "https://github.com/angmoo-tree/angmoo/security/advisories/new",
    ),
}


def _tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return [
            part.decode("utf-8", errors="surrogateescape")
            for part in result.stdout.split(b"\0")
            if part
        ]
    return [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not ({".git", ".venv", "node_modules", ".next"} & set(path.relative_to(root).parts))
    ]


def check_root(root: Path = ROOT) -> list[str]:
    errors = [
        f"obsolete two-repository path still exists: {relative}"
        for relative in sorted(FORBIDDEN_TRACKED_PATHS)
        if (root / relative).exists()
    ]
    for relative in sorted(ACTIVE_SURFACES):
        path = root / relative
        if not path.is_file():
            errors.append(f"missing contributor surface: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in sorted(STALE_MARKERS):
            if marker in text:
                errors.append(f"{relative}: stale hosted marker {marker}")
        for marker in REQUIRED_MARKERS.get(relative, ()):
            if marker not in text:
                errors.append(f"{relative}: missing Local OSS marker {marker}")
    for relative in _tracked_files(root):
        if "angmoo-private" in relative:
            errors.append(f"private repository path is tracked: {relative}")
    return errors


def main() -> int:
    errors = check_root(ROOT)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("Local OSS boundary check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
