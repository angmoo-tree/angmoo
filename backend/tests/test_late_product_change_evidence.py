"""Late evidence retains its ledger and follows the verified Git timeline."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


spec = importlib.util.spec_from_file_location(
    "late_product_changes", Path(__file__).resolve().parents[2] / "scripts/ci/post_refactor_contract_changes.py"
)
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)


def test_late_evidence_uses_real_git_topology_without_rewriting_or_skipping_steps(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, stderr=subprocess.PIPE).decode().strip()

    git("init", "--quiet")
    git("config", "user.name", "Synthetic contributor")
    git("config", "user.email", "synthetic@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("config", "core.autocrlf", "false")
    source = "frontend/package.json"
    path = tmp_path / source
    path.parent.mkdir()

    def commit(text, message):
        path.write_text(text, encoding="utf-8")
        git("add", "--", source)
        git("commit", "--quiet", "-m", message)
        return git("rev-parse", "HEAD")

    commit("v1\n", "initial")
    early = commit("v2\n", "early change")
    late = commit("v3\n", "late change")

    def record(sha, before, after):
        return {"id": sha, "implementation_commit": sha, "reason": "exact synthetic change",
                "review": "regression fixture", "source_blobs": {source: git("rev-parse", f"{sha}:{source}")},
                "frontend_files": [{"source": source, "before_sha256": changes.text_digest(before),
                                    "after_sha256": changes.text_digest(after)}]}

    late_record = record(late, "v2\n", "v3\n")
    early_record = record(early, "v1\n", "v2\n")
    manifest = tmp_path / changes.MANIFEST
    manifest.parent.mkdir()
    payload = {"schema_version": 1, "records": [late_record]}
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    git("add", "--", changes.MANIFEST)
    git("commit", "--quiet", "-m", "capture later change first")
    with pytest.raises(ValueError, match="chain preimage"):
        changes.frontend_matches(source, "v1\n", "v3\n", changes.load(tmp_path))

    payload["records"].append(early_record)
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    before = manifest.read_bytes()
    ordered = changes.load(tmp_path)
    assert manifest.read_bytes() == before
    assert [item["implementation_commit"] for item in ordered] == [early, late]
    assert payload["records"] == [late_record, early_record]
    assert changes.frontend_matches(source, "v1\n", "v3\n", ordered)
    assert not changes.frontend_matches(source, "v1\n", "unrecorded\n", ordered)

    early_record["frontend_files"][0]["before_sha256"] = changes.text_digest("invented\n")
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="committed preimage"):
        changes.load(tmp_path)
    early_record["frontend_files"][0]["before_sha256"] = changes.text_digest("v1\n")
    late_record["reason"] = "rewritten history"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="append-only"):
        changes.load(tmp_path)
