from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_m3_public_candidate.py"
SPEC = importlib.util.spec_from_file_location("angmoo_m3_candidate", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _repo_with_policy(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "candidate@example.test")
    _git(repo, "config", "user.name", "Candidate Test")
    (repo / "public").mkdir()
    (repo / "private").mkdir()
    (repo / "public" / "safe.txt").write_text("safe", encoding="utf-8")
    (repo / "private" / "secret.txt").write_text("private", encoding="utf-8")
    policy = repo / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "include_exact": [],
                "include_prefixes": ["public/"],
                "exclude_exact": [],
                "exclude_prefixes": ["private/"],
                "required_paths": ["public/safe.txt"],
            }
        ),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    return repo, policy


def test_candidate_is_built_from_committed_allowlisted_blobs(tmp_path: Path) -> None:
    repo, policy = _repo_with_policy(tmp_path)
    (repo / "public" / "safe.txt").write_text("dirty", encoding="utf-8")
    destination = tmp_path / "candidate"

    manifest = builder.build_candidate(
        repo_root=repo,
        ref="HEAD",
        destination=destination,
        policy_path=policy,
    )

    assert (destination / "public" / "safe.txt").read_text(encoding="utf-8") == "safe"
    assert not (destination / "private").exists()
    assert manifest["included_file_count"] == 1
    assert manifest["excluded_file_count"] == 1
    assert manifest["unclassified_file_count"] == 1
    assert manifest["provisional_only"] is True


def test_candidate_requires_a_new_destination(tmp_path: Path) -> None:
    repo, policy = _repo_with_policy(tmp_path)
    destination = tmp_path / "candidate"
    destination.mkdir()

    with pytest.raises(builder.CandidateBuildError, match="must not already exist"):
        builder.build_candidate(
            repo_root=repo,
            ref="HEAD",
            destination=destination,
            policy_path=policy,
        )
