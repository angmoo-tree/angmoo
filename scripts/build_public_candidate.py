"""Build a deterministic, history-free Angmoo public candidate from Git blobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = 1


class PublicExportError(RuntimeError):
    pass


def _git(repo_root: Path, *args: str, input_data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        input=input_data,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PublicExportError(detail or f"git {' '.join(args)} failed")
    return result.stdout


def _normalize_relative(value: str, *, label: str) -> str:
    if "\\" in value:
        raise PublicExportError(f"{label} must use forward slashes")
    pure = PurePosixPath(value)
    normalized = pure.as_posix()
    if (
        not value
        or pure.is_absolute()
        or normalized in {".", ""}
        or ".." in pure.parts
        or normalized != value
    ):
        raise PublicExportError(f"invalid {label}: {value!r}")
    return normalized


def _load_policy(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicExportError("public export policy could not be read") from exc
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise PublicExportError("unsupported public export policy schema")
    for key in ("mappings", "ignored_sources", "watched_prefixes", "required_destinations"):
        if not isinstance(policy.get(key), list):
            raise PublicExportError(f"public export policy {key} must be a list")
    if not isinstance(policy.get("watch_root_files", False), bool):
        raise PublicExportError("public export policy watch_root_files must be a boolean")
    return policy


def _tree_entries(repo_root: Path, commit: str) -> dict[str, tuple[str, str]]:
    output = _git(repo_root, "ls-tree", "-r", "-z", "--full-tree", commit)
    entries: dict[str, tuple[str, str]] = {}
    for raw in output.split(b"\0"):
        if not raw:
            continue
        try:
            metadata, path_bytes = raw.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
            source = path_bytes.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise PublicExportError("invalid Git tree entry") from exc
        if object_type == "blob":
            entries[source] = (mode, object_id)
    return entries


def _target_path(destination: Path, relative: str) -> Path:
    target = destination.joinpath(*PurePosixPath(relative).parts)
    try:
        target.resolve().relative_to(destination.resolve())
    except ValueError as exc:
        raise PublicExportError("destination path escapes export root") from exc
    return target


def _fresh_git(
    destination: Path, executable_paths: list[str]
) -> dict[str, str | int]:
    _git(destination, "init", "-q")
    _git(destination, "config", "user.email", "candidate@example.invalid")
    _git(destination, "config", "user.name", "Angmoo Public Export")
    _git(destination, "add", "--all")
    for path in executable_paths:
        _git(destination, "update-index", "--chmod=+x", "--", path)
    tree = _git(destination, "write-tree").decode("ascii").strip()
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
        }
    )
    result = subprocess.run(
        ["git", "commit", "-q", "-m", "Initial Angmoo public source"],
        cwd=destination,
        env=env,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PublicExportError(detail or "fresh Git root commit failed")
    commit = _git(destination, "rev-parse", "HEAD").decode("ascii").strip()
    count = int(_git(destination, "rev-list", "--count", "HEAD").decode("ascii").strip())
    parents = _git(destination, "rev-list", "--parents", "-n", "1", "HEAD").decode(
        "ascii"
    ).split()
    if count != 1 or len(parents) != 1:
        raise PublicExportError("fresh public Git repository must have one root commit")
    return {"fresh_git_tree": tree, "fresh_git_commit": commit, "fresh_git_commits": count}


def build_public_candidate(
    *,
    repo_root: Path,
    ref: str,
    destination: Path,
    policy_path: Path,
    report_path: Path | None = None,
    initialize_git: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    destination = destination.resolve()
    policy_path = policy_path.resolve()
    if destination.exists():
        raise PublicExportError("public export destination must not already exist")
    if report_path is not None:
        report_path = report_path.resolve()
        try:
            report_path.relative_to(destination)
        except ValueError:
            pass
        else:
            raise PublicExportError("private export report must remain outside candidate")

    policy = _load_policy(policy_path)
    commit = _git(repo_root, "rev-parse", f"{ref}^{{commit}}").decode("ascii").strip()
    source_tree = _git(repo_root, "rev-parse", f"{commit}^{{tree}}").decode(
        "ascii"
    ).strip()
    tree_entries = _tree_entries(repo_root, commit)

    mappings: list[tuple[str, str]] = []
    destinations: set[str] = set()
    mapped_sources: set[str] = set()
    for item in policy["mappings"]:
        if not isinstance(item, dict):
            raise PublicExportError("each public export mapping must be an object")
        source = _normalize_relative(str(item.get("source", "")), label="source")
        target = _normalize_relative(
            str(item.get("destination", "")), label="destination"
        )
        if target in destinations:
            raise PublicExportError(f"duplicate public destination: {target}")
        destinations.add(target)
        mapped_sources.add(source)
        mappings.append((source, target))

    ignored = {
        _normalize_relative(str(value), label="ignored source")
        for value in policy["ignored_sources"]
    }
    overlap = sorted(mapped_sources & ignored)
    if overlap:
        raise PublicExportError("sources cannot be mapped and ignored: " + ", ".join(overlap))
    watched_prefixes = tuple(
        _normalize_relative(str(value), label="watched prefix").rstrip("/") + "/"
        for value in policy["watched_prefixes"]
    )
    watch_root_files = policy.get("watch_root_files", False)
    required = {
        _normalize_relative(str(value), label="required destination")
        for value in policy["required_destinations"]
    }

    missing_sources = sorted((mapped_sources | ignored) - set(tree_entries))
    if missing_sources:
        raise PublicExportError(
            "policy references missing source files: " + ", ".join(missing_sources)
        )
    unclassified = sorted(
        source
        for source in tree_entries
        if (
            source.startswith(watched_prefixes)
            or (watch_root_files and "/" not in source)
        )
        and source not in mapped_sources
        and source not in ignored
    )
    if unclassified:
        raise PublicExportError(
            "watched source files are not classified: " + ", ".join(unclassified)
        )
    missing_required = sorted(required - destinations)
    if missing_required:
        raise PublicExportError(
            "required public destinations are not mapped: "
            + ", ".join(missing_required)
        )

    output_entries: list[dict[str, str]] = []
    destination.mkdir(parents=True)
    for source, target_name in sorted(mappings, key=lambda item: item[1]):
        mode, object_id = tree_entries[source]
        if mode == "120000":
            raise PublicExportError(f"symlink source is forbidden: {source}")
        if mode not in {"100644", "100755"}:
            raise PublicExportError(f"unsupported Git mode {mode}: {source}")
        content = _git(repo_root, "cat-file", "blob", object_id)
        target = _target_path(destination, target_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        if mode == "100755":
            target.chmod(target.stat().st_mode | 0o111)
        output_entries.append(
            {
                "destination": target_name,
                "mode": mode,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    manifest_bytes = (
        json.dumps(output_entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    content_hasher = hashlib.sha256()
    for entry in output_entries:
        content_hasher.update(entry["destination"].encode("utf-8"))
        content_hasher.update(b"\0")
        content_hasher.update(entry["mode"].encode("ascii"))
        content_hasher.update(b"\0")
        content_hasher.update(entry["sha256"].encode("ascii"))
        content_hasher.update(b"\n")

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_commit": commit,
        "source_tree": source_tree,
        "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        "candidate_content_sha256": content_hasher.hexdigest(),
        "candidate_manifest_sha256": manifest_sha256,
        "included_file_count": len(output_entries),
        "ignored_file_count": len(ignored),
        "unclassified_file_count": 0,
        "entries": output_entries,
    }
    if initialize_git:
        report.update(
            _fresh_git(
                destination,
                [
                    entry["destination"]
                    for entry in output_entries
                    if entry["mode"] == "100755"
                ],
            )
        )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("backend/security/m4_private_export_policy.json"),
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fresh-git", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    policy = args.policy if args.policy.is_absolute() else repo_root / args.policy
    try:
        report = build_public_candidate(
            repo_root=repo_root,
            ref=args.ref,
            destination=args.destination,
            policy_path=policy,
            report_path=args.report,
            initialize_git=args.fresh_git,
        )
    except PublicExportError as exc:
        print(f"Public export failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Public export passed: "
        f"files={report['included_file_count']} "
        f"content_sha256={report['candidate_content_sha256']} "
        f"manifest_sha256={report['candidate_manifest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
