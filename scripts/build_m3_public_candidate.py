from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any


SCHEMA_VERSION = 1
MANIFEST_NAME = ".angmoo-m3-candidate-manifest.json"


class CandidateBuildError(RuntimeError):
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
        raise CandidateBuildError(detail or f"git {' '.join(args)} failed")
    return result.stdout


def _load_policy(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateBuildError("candidate policy could not be read") from exc
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise CandidateBuildError("unsupported candidate policy schema")
    for key in (
        "include_exact",
        "include_prefixes",
        "exclude_exact",
        "exclude_prefixes",
        "required_paths",
    ):
        values = policy.get(key)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            raise CandidateBuildError(f"candidate policy {key} must be a string list")
    return policy


def _matches(path: str, exact: set[str], prefixes: tuple[str, ...]) -> bool:
    return path in exact or any(path.startswith(prefix) for prefix in prefixes)


def _tree_entries(repo_root: Path, commit: str) -> list[tuple[str, str, str]]:
    output = _git(repo_root, "ls-tree", "-r", "-z", commit)
    entries: list[tuple[str, str, str]] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        try:
            metadata, path_bytes = raw.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
            path = path_bytes.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise CandidateBuildError("invalid Git tree entry") from exc
        if object_type != "blob":
            continue
        entries.append((mode, object_id, path))
    return entries


def _destination_path(destination: Path, source_path: str) -> Path:
    pure = PurePosixPath(source_path)
    if pure.is_absolute() or ".." in pure.parts:
        raise CandidateBuildError("candidate path escapes destination")
    target = destination.joinpath(*pure.parts)
    try:
        target.resolve().relative_to(destination.resolve())
    except ValueError as exc:
        raise CandidateBuildError("candidate path escapes destination") from exc
    return target


def build_candidate(
    *,
    repo_root: Path,
    ref: str,
    destination: Path,
    policy_path: Path,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    destination = destination.resolve()
    policy_path = policy_path.resolve()
    if destination.exists():
        raise CandidateBuildError("candidate destination must not already exist")

    policy = _load_policy(policy_path)
    commit = _git(repo_root, "rev-parse", f"{ref}^{{commit}}").decode("ascii").strip()
    source_tree = _git(repo_root, "rev-parse", f"{commit}^{{tree}}").decode("ascii").strip()
    entries = _tree_entries(repo_root, commit)

    include_exact = set(policy["include_exact"])
    include_prefixes = tuple(policy["include_prefixes"])
    exclude_exact = set(policy["exclude_exact"])
    exclude_prefixes = tuple(policy["exclude_prefixes"])
    required = set(policy["required_paths"])

    included: list[tuple[str, str]] = []
    excluded_count = 0
    unclassified_count = 0
    for mode, object_id, source_path in entries:
        if _matches(source_path, exclude_exact, exclude_prefixes):
            excluded_count += 1
            continue
        if not _matches(source_path, include_exact, include_prefixes):
            unclassified_count += 1
            continue
        if mode == "120000":
            raise CandidateBuildError("symlinks are not allowed in the candidate")
        if mode not in {"100644", "100755"}:
            raise CandidateBuildError("unsupported Git file mode in candidate")
        included.append((source_path, object_id))

    included_paths = {path for path, _ in included}
    missing = sorted(required - included_paths)
    if missing:
        raise CandidateBuildError(
            "required candidate paths are missing: " + ", ".join(missing)
        )

    destination.mkdir(parents=True)
    for source_path, _ in included:
        target = _destination_path(destination, source_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git(repo_root, "cat-file", "blob", f"{commit}:{source_path}"))

    digest_input = "".join(
        f"{path}\0{object_id}\n" for path, object_id in sorted(included)
    ).encode("utf-8")
    policy_sha256 = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    content_sha256 = hashlib.sha256(digest_input).hexdigest()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "provisional_only": True,
        "source_commit": commit,
        "source_tree": source_tree,
        "policy_sha256": policy_sha256,
        "candidate_content_sha256": content_sha256,
        "included_file_count": len(included),
        "excluded_file_count": excluded_count,
        "unclassified_file_count": unclassified_count,
        "included_files": [
            {"path": path, "blob": object_id} for path, object_id in sorted(included)
        ],
    }
    (destination / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a provisional deny-by-default M3 public audit candidate."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("backend/security/m3_public_candidate_policy.json"),
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    policy = args.policy
    if not policy.is_absolute():
        policy = repo_root / policy
    try:
        manifest = build_candidate(
            repo_root=repo_root,
            ref=args.ref,
            destination=args.destination,
            policy_path=policy,
        )
    except CandidateBuildError as exc:
        print(f"M3 candidate build failed: {exc}")
        return 1
    print(
        "M3 candidate built: "
        f"commit={manifest['source_commit']} "
        f"files={manifest['included_file_count']} "
        f"excluded={manifest['excluded_file_count']} "
        f"unclassified={manifest['unclassified_file_count']} "
        f"content_sha256={manifest['candidate_content_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
