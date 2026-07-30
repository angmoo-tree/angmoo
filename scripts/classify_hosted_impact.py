"""Classify a public Git diff without starting private validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Iterable


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ZERO_SHA = "0" * 40


class HostedImpactError(RuntimeError):
    pass


def _normalize_path(value: str) -> str:
    if not value or "\0" in value or "\\" in value:
        raise HostedImpactError(f"invalid changed path: {value!r}")
    path = PurePosixPath(value)
    normalized = path.as_posix()
    if (
        path.is_absolute()
        or normalized in {"", "."}
        or ".." in path.parts
        or normalized != value
        or re.match(r"^[A-Za-z]:", value)
    ):
        raise HostedImpactError(f"invalid changed path: {value!r}")
    return normalized


def _load_policy(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HostedImpactError("hosted impact policy could not be read") from exc
    severities = policy.get("severity_order")
    rules = policy.get("rules")
    if (
        policy.get("schema_version") != 1
        or severities != ["public-only", "hosted-fast", "hosted-full"]
        or not isinstance(rules, list)
    ):
        raise HostedImpactError("unsupported hosted impact policy")
    for rule in rules:
        if (
            not isinstance(rule, dict)
            or rule.get("classification") not in severities
            or not isinstance(rule.get("exact"), list)
            or not isinstance(rule.get("prefixes"), list)
        ):
            raise HostedImpactError("invalid hosted impact rule")
        if not all(isinstance(value, str) for value in rule["exact"]):
            raise HostedImpactError("invalid hosted impact exact path")
        if not all(isinstance(value, str) for value in rule["prefixes"]):
            raise HostedImpactError("invalid hosted impact prefix")
        rule["exact"] = [_normalize_path(value) for value in rule["exact"]]
        rule["prefixes"] = [
            _normalize_path(value.rstrip("/")) + "/"
            for value in rule["prefixes"]
        ]
    return policy


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise HostedImpactError(detail or "Git diff failed")
    return result.stdout


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    if not FULL_SHA.fullmatch(head):
        raise HostedImpactError("head must be a full 40-character commit SHA")
    if base != ZERO_SHA and not FULL_SHA.fullmatch(base):
        raise HostedImpactError("base must be a full 40-character commit SHA")
    if base == ZERO_SHA:
        raw = _git(
            repo,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-z",
            head,
        )
    else:
        raw = _git(repo, "diff", "--name-status", "-z", base, head)
    fields = raw.decode("utf-8").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if not status:
            continue
        path_count = 2 if status[0] in {"R", "C"} else 1
        if index + path_count > len(fields):
            raise HostedImpactError("invalid Git diff output")
        paths.extend(fields[index:index + path_count])
        index += path_count
    return paths


def classify_paths(paths: Iterable[str], policy: dict[str, Any]) -> dict[str, Any]:
    normalized: list[str] = []
    folded: dict[str, str] = {}
    for raw in paths:
        path = _normalize_path(raw)
        previous = folded.setdefault(path.casefold(), path)
        if previous != path:
            raise HostedImpactError(
                f"case-insensitive changed-path collision: {previous!r}, {path!r}"
            )
        if path not in normalized:
            normalized.append(path)

    severities: list[str] = policy["severity_order"]
    rank = {name: index for index, name in enumerate(severities)}
    classified: list[dict[str, str]] = []
    unclassified: list[str] = []
    for path in sorted(normalized):
        matches: list[str] = []
        for rule in policy["rules"]:
            if path in rule["exact"] or any(
                path.startswith(prefix) for prefix in rule["prefixes"]
            ):
                matches.append(rule["classification"])
        if not matches:
            unclassified.append(path)
            continue
        classified.append(
            {"path": path, "classification": max(matches, key=rank.__getitem__)}
        )

    if unclassified:
        raise HostedImpactError(
            "unclassified changed paths: " + ", ".join(unclassified)
        )
    overall = max(
        (entry["classification"] for entry in classified),
        key=rank.__getitem__,
        default="public-only",
    )
    return {
        "schema_version": 1,
        "hosted_impact": overall,
        "changed_path_count": len(classified),
        "unclassified_count": 0,
        "private_workflow_started": False,
        "paths": classified,
    }


def _write_github_output(path: Path, result: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"hosted_impact={result['hosted_impact']}\n")
        handle.write("unclassified_count=0\n")
        handle.write("private_workflow_started=false\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("security/hosted_impact_policy.json"),
    )
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        policy = _load_policy(args.policy)
        if args.path:
            if args.base or args.head:
                raise HostedImpactError(
                    "--path cannot be combined with --base or --head"
                )
            paths = args.path
        else:
            if not args.base or not args.head:
                raise HostedImpactError("--base and --head are required")
            paths = changed_paths(args.repo, args.base, args.head)
        result = classify_paths(paths, policy)
        if args.github_output:
            _write_github_output(args.github_output, result)
    except (HostedImpactError, OSError) as exc:
        print(f"Hosted impact classification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
