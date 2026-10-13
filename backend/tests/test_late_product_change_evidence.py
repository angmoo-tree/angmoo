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


def committed_history_fixture(root):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE).decode().strip()
    git("init", "--quiet")
    git("config", "user.name", "Synthetic contributor")
    git("config", "user.email", "synthetic@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("config", "core.autocrlf", "false")
    source = root / "source.py"
    source.write_text("def value(): return 1\n", encoding="utf-8")
    git("add", "--", "source.py")
    git("commit", "--quiet", "-m", "synthetic source")
    implementation = git("rev-parse", "HEAD")
    record = {"id": "first", "implementation_commit": implementation, "reason": "actual source",
              "review": "synthetic regression", "source_blobs": {"source.py": git("rev-parse", "HEAD:source.py")}}
    manifest = root / changes.MANIFEST
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"schema_version": 1, "records": [record]}), encoding="utf-8")
    git("add", "--", changes.MANIFEST)
    git("commit", "--quiet", "-m", "capture source evidence")
    return git, manifest, record


def test_pinned_history_bytes_stay_exact_while_new_head_is_revalidated(tmp_path):
    git, manifest, first = committed_history_fixture(tmp_path)
    old_object = git("rev-parse", "HEAD") + ":" + changes.MANIFEST
    original = subprocess.check_output(["git", "show", old_object], cwd=tmp_path)
    assert changes.committed_history_bytes(tmp_path, old_object) == original
    assert changes.load(tmp_path) == [first]
    (tmp_path / "source.py").write_text("def value(): return 2\n", encoding="utf-8")
    git("add", "--", "source.py")
    git("commit", "--quiet", "-m", "second source")
    second = {**first, "id": "second", "implementation_commit": git("rev-parse", "HEAD"),
              "source_blobs": {"source.py": git("rev-parse", "HEAD:source.py")}}
    manifest.write_text(json.dumps({"schema_version": 1, "records": [first, second]}), encoding="utf-8")
    git("add", "--", changes.MANIFEST)
    git("commit", "--quiet", "-m", "append second source evidence")
    assert changes.load(tmp_path) == [first, second]
    assert changes.committed_history_bytes(tmp_path, old_object) == original
    with pytest.raises(ValueError, match="exact committed ledger"):
        changes.committed_history_bytes(tmp_path, "HEAD:" + changes.MANIFEST)


def test_warm_history_never_accepts_changed_candidate_prefix(tmp_path):
    _, manifest, first = committed_history_fixture(tmp_path)
    assert changes.load(tmp_path) == [first]
    manifest.write_text(json.dumps({"schema_version": 1, "records": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="append-only"):
        changes.load(tmp_path)


def test_warm_native_history_does_not_hide_injected_reader_or_other_repo(tmp_path):
    git, _, first = committed_history_fixture(tmp_path)
    assert changes.load(tmp_path) == [first]
    def changed_reader(*args, root):
        result = subprocess.check_output(["git", *args], cwd=root)
        if len(args) == 2 and args[0] == "show" and args[1].endswith(":" + changes.MANIFEST):
            value = json.loads(result)
            value["records"][0]["reason"] = "altered history"
            return json.dumps(value).encode()
        return result
    with pytest.raises(ValueError, match="append-only"):
        changes.load(tmp_path, reader=changed_reader)
    other = tmp_path / "independent"
    other.mkdir()
    subprocess.check_output(["git", "init", "--quiet"], cwd=other)
    with pytest.raises(subprocess.CalledProcessError):
        changes.committed_history_bytes(other, git("rev-parse", "HEAD") + ":" + changes.MANIFEST)


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
