"""Pinned Git objects are immutable; mutable refs and readers are not."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("preservation_cache", ROOT / "scripts/ci/check_refactor_preservation.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
SHA = "a" * 40
OTHER = "b" * 40


@pytest.mark.parametrize("args,immutable", [
    (("cat-file", "blob", SHA), True),
    (("show", SHA + ":backend/app/fixture.py"), True),
    (("show", SHA + "^:backend/app/fixture.py"), True),
    (("show", SHA + ":security/refactor_backend_additions.json"), False),
    (("show", "HEAD:backend/app/fixture.py"), False),
    (("merge-base", "--is-ancestor", SHA, OTHER), True),
    (("merge-base", "--is-ancestor", SHA, "HEAD"), False),
    (("log", "--reverse", "--format=%H", "--diff-filter=A", SHA + ".." + OTHER, "--", "fixture.py"), True),
    (("log", "--format=%H", SHA + "..HEAD", "--", "fixture.py"), False),
    (("rev-parse", "HEAD"), False),
    (("diff", "--", "fixture.py"), False),
])
def test_only_pinned_object_or_range_reads_are_cacheable(args, immutable):
    assert checker.immutable_git_read(args) is immutable


def test_actual_head_changes_are_reread_and_original_blob_stays_pinned(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path)
    git("init", "-q")
    source = tmp_path / "fixture.txt"
    source.write_text("original", encoding="utf8")
    git("add", "--", "fixture.txt")
    git("-c", "user.name=Local test", "-c", "user.email=local@example.invalid", "commit", "-q", "-m", "original")
    original = git("rev-parse", "HEAD").decode().strip()
    checker._immutable_git_bytes.cache_clear()
    assert checker.git_bytes("show", "HEAD:fixture.txt", root=tmp_path) == b"original"
    assert checker.git_bytes("show", original + ":fixture.txt", root=tmp_path) == b"original"
    assert checker.git_bytes("show", original + ":fixture.txt", root=tmp_path) == b"original"
    assert checker._immutable_git_bytes.cache_info().hits == 1
    source.write_text("changed", encoding="utf8")
    git("add", "--", "fixture.txt")
    git("-c", "user.name=Local test", "-c", "user.email=local@example.invalid", "commit", "-q", "-m", "changed")
    assert checker.git_bytes("show", "HEAD:fixture.txt", root=tmp_path) == b"changed"
    assert checker.git_bytes("show", original + ":fixture.txt", root=tmp_path) == b"original"
    assert checker.git_bytes("rev-parse", "HEAD", root=tmp_path).decode().strip() != original


def test_injected_reader_is_never_cached(monkeypatch, tmp_path):
    values = iter([b"first", b"second"])
    monkeypatch.setattr(checker.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, next(values), b""))
    assert checker.git_bytes("show", SHA + ":fixture.txt", root=tmp_path) == b"first"
    assert checker.git_bytes("show", SHA + ":fixture.txt", root=tmp_path) == b"second"
