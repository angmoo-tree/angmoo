"""Real adapter boundaries: draft discovery and immutable product selection."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.release.publish import ReleaseAPI, verify_product_checkout
from scripts.release.workflow_policy import validate

TAG = "release-v0.1.0"


@pytest.mark.parametrize("draft", [True, False])
def test_list_finds_exact_draft_or_published_release_beyond_first_page(monkeypatch, draft):
    calls = []
    target = {"id": 42, "tag_name": TAG, "draft": draft, "assets": [{"id": 7}]}
    pages = [[{"id": n, "tag_name": "unrelated-" + str(n)} for n in range(100)], [target]]
    def request(args, **kwargs):
        calls.append(args)
        assert args[:2] == ["gh", "api"]
        assert args[2].endswith("releases?per_page=100&page=" + str(len(calls)))
        return subprocess.CompletedProcess(args, 0, json.dumps(pages[len(calls) - 1]).encode(), b"")
    monkeypatch.setattr(subprocess, "run", request)
    assert ReleaseAPI().find(TAG) == target
    assert len(calls) == 2


def test_lookup_failure_is_not_treated_as_absence(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 1, b"", b"HTTP 403"))
    with pytest.raises(ValueError, match="release_lookup_failed"):
        ReleaseAPI().find(TAG)


@pytest.mark.parametrize("value,error", [
    ({"message": "not a list"}, "release_lookup_invalid"),
    ([{"tag_name": TAG, "id": 1}, {"tag_name": TAG, "id": 2}], "release_tag_ambiguous"),
])
def test_malformed_or_ambiguous_release_is_rejected(monkeypatch, value, error):
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, json.dumps(value).encode(), b""))
    with pytest.raises(ValueError, match=error):
        ReleaseAPI().find(TAG)


def test_missing_release_requires_complete_successful_enumeration(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, b"[]", b""))
    assert ReleaseAPI().find(TAG) is None


def test_pagination_exhaustion_is_not_absence(monkeypatch):
    page = json.dumps([{"tag_name": "other"}] * 100).encode()
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, page, b""))
    with pytest.raises(ValueError, match="release_pagination_limit"):
        ReleaseAPI().find(TAG)


def test_product_checkout_requires_exact_clean_git_root(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()
    git("init", "--quiet")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Release fixture")
    (tmp_path / "adapter.py").write_text("original")
    git("add", "adapter.py")
    git("commit", "--quiet", "-m", "synthetic product")
    sha = git("rev-parse", "HEAD")
    assert verify_product_checkout(tmp_path, sha) == tmp_path.resolve()
    with pytest.raises(ValueError, match="release_checkout_source_mismatch"):
        verify_product_checkout(tmp_path, "0" * 40)
    (tmp_path / "adapter.py").write_text("changed")
    with pytest.raises(ValueError, match="release_product_checkout_dirty"):
        verify_product_checkout(tmp_path, sha)
    (tmp_path / "subdir").mkdir()
    with pytest.raises(ValueError, match="release_product_root_invalid"):
        verify_product_checkout(tmp_path / "subdir", sha)


def test_release_workflow_keeps_main_tools_and_verified_product_separate():
    import yaml
    original = yaml.safe_load((ROOT / ".github/workflows/release-publish.yml").read_text())
    assert validate(original, "release-publish.yml") == []
    for mutate in ("root", "workdir", "source", "guard"):
        doc = copy.deepcopy(original)
        steps = doc["jobs"]["publish"]["steps"]
        if mutate == "root":
            doc["env"]["RELEASE_PRODUCT_ROOT"] = "${{ github.workspace }}/release-tools"
        elif mutate == "workdir":
            doc["defaults"]["run"]["working-directory"] = "product"
        elif mutate == "source":
            steps[2]["with"]["ref"] = "main"
        else:
            steps.pop(1)
        assert validate(doc, "release-publish.yml")
