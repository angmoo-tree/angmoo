"""Require DCO 1.1 trailers for human commits in a Git range."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import os
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA = "0" * 40
SIGNOFF = re.compile(
    r"(?mi)^Signed-off-by:\s+.+?\s+<[^<>@\s]+@[^<>\s]+>\s*$"
)
DEPENDABOT_NAMES = {"dependabot[bot]"}
DEPENDABOT_EMAILS = {"49699333+dependabot[bot]@users.noreply.github.com"}


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    author_name: str
    author_email: str
    body: str


def _git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _dependabot_path_allowed(path: str) -> bool:
    pure = PurePosixPath(path)
    if path in {
        ".github/dependabot.yml",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "frontend/package.json",
        "frontend/pnpm-lock.yaml",
        "compose.yml",
    }:
        return True
    return pure.parts[:2] == (".github", "workflows") and pure.suffix in {
        ".yml",
        ".yaml",
    }


def validate_record(
    record: CommitRecord, paths: list[str], *, actor: str = ""
) -> list[str]:
    if SIGNOFF.search(record.body):
        return []
    is_dependabot = (
        record.author_name in DEPENDABOT_NAMES
        and record.author_email in DEPENDABOT_EMAILS
    )
    if (
        is_dependabot
        and actor == "dependabot[bot]"
        and paths
        and all(_dependabot_path_allowed(path) for path in paths)
    ):
        return []
    if is_dependabot:
        return ["Dependabot exception rejected because changed paths are too broad"]
    return ["missing valid Signed-off-by trailer"]


def _resolve_base(root: Path, base: str, head: str) -> str | None:
    if base and base != ZERO_SHA and _git(root, "cat-file", "-e", f"{base}^{{commit}}", check=False) == "":
        result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{base}^{{commit}}"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return base
    parent = _git(root, "rev-parse", f"{head}^", check=False)
    return parent or None


def check_range(
    root: Path, base: str, head: str, *, actor: str = ""
) -> list[str]:
    resolved_base = _resolve_base(root, base, head)
    if resolved_base is None:
        return []
    commits = _git(root, "rev-list", "--reverse", "--no-merges", f"{resolved_base}..{head}")
    errors: list[str] = []
    for sha in (line for line in commits.splitlines() if line):
        raw = _git(root, "show", "-s", "--format=%an%x00%ae%x00%B", sha)
        author_name, author_email, body = raw.split("\x00", 2)
        paths = [
            line
            for line in _git(
                root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha
            ).splitlines()
            if line
        ]
        record = CommitRecord(sha, author_name, author_email, body)
        errors.extend(
            f"{sha[:12]}: {error}"
            for error in validate_record(record, paths, actor=actor)
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    try:
        errors = check_range(
            args.repo_root.resolve(),
            args.base.strip(),
            args.head.strip(),
            actor=os.getenv("GITHUB_ACTOR", ""),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"DCO check failed: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("DCO check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
