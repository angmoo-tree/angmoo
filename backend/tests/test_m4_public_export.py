from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORTER_PATH = REPO_ROOT / "scripts" / "build_public_candidate.py"
SPEC = importlib.util.spec_from_file_location("angmoo_public_export", EXPORTER_PATH)
assert SPEC is not None and SPEC.loader is not None
exporter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = exporter
SPEC.loader.exec_module(exporter)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _fixture_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (repo / "src").mkdir()
    (repo / "private").mkdir()
    (repo / "src" / "safe.txt").write_text("committed\n", encoding="utf-8")
    (repo / "src" / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "private" / "ignored.txt").write_text("private\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "update-index", "--chmod=+x", "src/run.sh")
    _git(repo, "commit", "-q", "-m", "fixture")

    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mappings": [
                    {"source": "src/safe.txt", "destination": "README.md"},
                    {"source": "src/run.sh", "destination": "scripts/run.sh"},
                ],
                "ignored_sources": [],
                "watched_prefixes": ["src"],
                "watch_root_files": False,
                "required_destinations": ["README.md", "scripts/run.sh"],
            }
        ),
        encoding="utf-8",
    )
    return repo, policy


def test_export_uses_committed_blobs_preserves_mode_and_creates_root_git(
    tmp_path: Path,
) -> None:
    repo, policy = _fixture_repo(tmp_path)
    (repo / "src" / "safe.txt").write_text("dirty\n", encoding="utf-8")
    candidate = tmp_path / "candidate"
    report_path = tmp_path / "report.json"

    report = exporter.build_public_candidate(
        repo_root=repo,
        ref="HEAD",
        destination=candidate,
        policy_path=policy,
        report_path=report_path,
        initialize_git=True,
    )

    assert (candidate / "README.md").read_text(encoding="utf-8") == "committed\n"
    assert report["included_file_count"] == 2
    assert report["unclassified_file_count"] == 0
    assert report["fresh_git_commits"] == 1
    assert _git(candidate, "rev-list", "--parents", "-n", "1", "HEAD").count(" ") == 0
    assert _git(candidate, "ls-files", "-s", "scripts/run.sh").startswith("100755 ")
    assert report_path.exists()
    assert not (candidate / "report.json").exists()


def test_export_rejects_existing_destination(tmp_path: Path) -> None:
    repo, policy = _fixture_repo(tmp_path)
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    with pytest.raises(exporter.PublicExportError, match="must not already exist"):
        exporter.build_public_candidate(
            repo_root=repo,
            ref="HEAD",
            destination=candidate,
            policy_path=policy,
        )


def test_export_rejects_new_unclassified_watched_file(tmp_path: Path) -> None:
    repo, policy = _fixture_repo(tmp_path)
    (repo / "src" / "new.txt").write_text("new\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "new public file")

    with pytest.raises(exporter.PublicExportError, match="not classified"):
        exporter.build_public_candidate(
            repo_root=repo,
            ref="HEAD",
            destination=tmp_path / "candidate",
            policy_path=policy,
        )


def test_export_rejects_new_unclassified_root_file(tmp_path: Path) -> None:
    repo, policy = _fixture_repo(tmp_path)
    payload = json.loads(policy.read_text(encoding="utf-8"))
    payload["watch_root_files"] = True
    policy.write_text(json.dumps(payload), encoding="utf-8")
    (repo / "unexpected.txt").write_text("new\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "new root file")

    with pytest.raises(exporter.PublicExportError, match="not classified"):
        exporter.build_public_candidate(
            repo_root=repo,
            ref="HEAD",
            destination=tmp_path / "candidate",
            policy_path=policy,
        )


def test_attested_svg_keeps_lf_with_windows_autocrlf(tmp_path: Path) -> None:
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert attributes.splitlines() == [
        "frontend/src/app/icon.svg text eol=lf",
    ]

    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "fixture@example.invalid")
    _git(source, "config", "user.name", "Fixture")
    (source / "frontend/src/app").mkdir(parents=True)
    (source / ".gitattributes").write_text(attributes, encoding="utf-8")
    (source / "frontend/src/app/icon.svg").write_bytes(
        (REPO_ROOT / "frontend/src/app/icon.svg").read_bytes()
    )
    _git(source, "add", ".")
    _git(source, "commit", "-q", "-m", "fixture")

    checkout = tmp_path / "checkout"
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=true",
            "clone",
            "--no-local",
            str(source),
            str(checkout),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    manifest = json.loads(
        (REPO_ROOT / "backend/security/asset_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    expected = next(
        item["sha256"]
        for item in manifest["assets"]
        if item["path"] == "frontend/src/app/icon.svg"
    )
    payload = (checkout / "frontend/src/app/icon.svg").read_bytes()
    assert b"\r\n" not in payload
    assert hashlib.sha256(payload).hexdigest() == expected


def test_public_policy_exports_checkout_attributes() -> None:
    policy = json.loads(
        (REPO_ROOT / "security/public_export_policy.json").read_text(
            encoding="utf-8"
        )
    )
    mappings = {
        item["source"]: item["destination"]
        for item in policy["mappings"]
    }
    assert mappings[".gitattributes"] == ".gitattributes"


@pytest.mark.skipif(sys.platform == "win32", reason="Git symlink fixture needs POSIX")
def test_export_rejects_symlink_source(tmp_path: Path) -> None:
    repo, policy = _fixture_repo(tmp_path)
    (repo / "src" / "safe.txt").unlink()
    (repo / "src" / "safe.txt").symlink_to("../private/ignored.txt")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "symlink")

    with pytest.raises(exporter.PublicExportError, match="symlink"):
        exporter.build_public_candidate(
            repo_root=repo,
            ref="HEAD",
            destination=tmp_path / "candidate",
            policy_path=policy,
        )


def test_export_rejects_destination_collision(tmp_path: Path) -> None:
    repo, policy = _fixture_repo(tmp_path)
    payload = json.loads(policy.read_text(encoding="utf-8"))
    payload["mappings"][1]["destination"] = "README.md"
    policy.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(exporter.PublicExportError, match="duplicate public destination"):
        exporter.build_public_candidate(
            repo_root=repo,
            ref="HEAD",
            destination=tmp_path / "candidate",
            policy_path=policy,
        )
