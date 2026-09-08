from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "post_refactor_changes", Path(__file__).resolve().parents[2] / "scripts/ci/post_refactor_contract_changes.py"
)
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)


def test_only_named_contract_changes_apply_and_original_snapshot_is_immutable():
    original = {"full": {"schemas": {"Persona": "old", "Other": "untouched"}}}
    record = {"contracts": [{"application": "full", "kind": "schemas", "key": "Persona", "before": "old", "after": "new"}]}
    expected = changes.contracts(original, [record])
    assert original["full"]["schemas"]["Persona"] == "old"
    assert expected["full"]["schemas"] == {"Persona": "new", "Other": "untouched"}
    drifted = deepcopy(expected)
    drifted["full"]["schemas"]["Other"] = "unapproved"
    assert drifted != expected
    record["contracts"][0]["before"] = "different"
    with pytest.raises(ValueError, match="preimage"):
        changes.contracts(original, [record])


def test_orm_and_duplicate_changes_cannot_be_excused():
    entry = {"application": "full", "kind": "orm_tables", "key": "Persona", "before": "old", "after": "new"}
    with pytest.raises(ValueError, match="ORM"):
        changes.contracts({}, [{"contracts": [entry]}])
    entry["kind"] = "schemas"
    with pytest.raises(ValueError, match="duplicate"):
        changes.contracts({"full": {"schemas": {"Persona": "old"}}}, [{"contracts": [entry, entry]}])


def test_assertion_change_requires_exact_before_after_and_keeps_other_nodes():
    record = {"assertions": [{"node": "test.py::test_change", "before": ["old", "safety"], "after": ["new", "safety"]}]}
    before, after = Counter(["old", "safety"]), Counter(["new", "safety"])
    assert changes.assertions("test.py::test_change", before, after, [record]) == after
    assert changes.assertions("test.py::test_other", before, after, [record]) == before
    with pytest.raises(ValueError, match="before/after"):
        changes.assertions("test.py::test_change", before, Counter(["new"]), [record])
    with pytest.raises(ValueError, match="before/after"):
        changes.assertions("test.py::test_change", Counter(["changed-old"]), after, [record])


def test_manifest_requires_committed_provenance_and_append_only_history(tmp_path, monkeypatch):
    commit, blob = "a" * 40, "b" * 40
    record = {"id": "example", "implementation_commit": commit, "reason": "reviewed", "review": "PR",
              "source_blobs": {"backend/example.py": blob}, "contracts": [], "assertions": []}
    payload = {"schema_version": 1, "records": [record]}
    path = tmp_path / changes.MANIFEST
    path.parent.mkdir()
    path.write_text(json.dumps(payload), encoding="utf-8")
    def git(args, **kwargs):
        if args[1] == "log":
            return b"historical\n"
        if args[1] == "show":
            return json.dumps(payload).encode()
        if args[1] == "merge-base":
            return b""
        assert args[1] == "rev-parse"
        return blob.encode()
    monkeypatch.setattr(changes.subprocess, "check_output", git)
    assert changes.load(tmp_path) == [record]
    altered = deepcopy(payload)
    altered["records"][0]["reason"] = "rewritten"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError, match="append-only"):
        changes.load(tmp_path)
    path.write_text(json.dumps(payload), encoding="utf-8")
    blob = "c" * 40
    with pytest.raises(ValueError, match="provenance"):
        changes.load(tmp_path)
