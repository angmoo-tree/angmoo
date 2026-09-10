from collections import Counter
import ast
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


def test_named_definition_delta_cannot_approve_a_different_owner_or_body(tmp_path):
    old = ast.parse("def choose():\n    return 'high'\n").body[0]
    new = ast.parse("def choose():\n    return 'medium'\n").body[0]
    drift = ast.parse("def choose():\n    return 'low'\n").body[0]
    records = [{"definitions": [{"source": "backend/profile.py", "symbol": "choose",
        "before_ast": ast.dump(old, include_attributes=False),
        "after_ast": ast.dump(new, include_attributes=False)}]}]
    assert changes.definition_matches(tmp_path, "backend/profile.py", "choose", old, new, records=records)
    assert not changes.definition_matches(tmp_path, "backend/profile.py", "choose", old, drift, records=records)
    assert not changes.definition_matches(tmp_path, "backend/other.py", "choose", old, new, records=records)
    assert not changes.definition_matches(tmp_path, "backend/profile.py", "other", old, new, records=records)


def test_ast_evidence_normalizes_empty_fields_but_never_executes_calls():
    node = ast.parse("def choose():\n    return 'high'\n").body[0]
    assert changes.normalize_ast_dump(ast.dump(node, show_empty=True)) == ast.dump(node)
    with pytest.raises(ValueError, match="constructor"):
        changes.normalize_ast_dump("Module(body=[__import__('os').getcwd()])")


def test_exact_orm_delta_preserves_other_tables_and_rejects_changed_preimage():
    original = {"orm_tables": {"profiles": "old", "secrets": "untouched"}}
    record = {"orm_tables": [{"key": "profiles", "before": "old", "after": "new"}]}
    assert changes.contracts(original, [record]) == {"orm_tables": {"profiles": "new", "secrets": "untouched"}}
    assert original["orm_tables"]["profiles"] == "old"
    record["orm_tables"][0]["before"] = "tampered"
    with pytest.raises(ValueError, match="ORM preimage"):
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


def test_assertion_chain_checks_every_transition_and_exact_final_state():
    records = [
        {"assertions": [{"node": "test.py::test_change", "before": ["v9", "safety"], "after": ["v10", "safety"]}]},
        {"assertions": [{"node": "test.py::test_change", "before": ["v10", "safety"], "after": ["v11", "safety"]}]},
    ]
    final = Counter(["v11", "safety"])
    assert changes.assertions("test.py::test_change", Counter(["v9", "safety"]), final, records) == final
    assert changes.assertions("test.py::test_change", Counter(["v10", "safety"]), final, records) == final
    with pytest.raises(ValueError, match="before/after"):
        changes.assertions("test.py::test_change", Counter(["v9", "safety"]), Counter(["v11"]), records)
    broken = deepcopy(records)
    broken[1]["assertions"][0]["before"] = ["unreviewed", "safety"]
    with pytest.raises(ValueError, match="before/after"):
        changes.assertions("test.py::test_change", Counter(["v9", "safety"]), final, broken)


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


@pytest.mark.parametrize("tamper", [None, "parent", "commit", "current", "untracked"])
def test_removed_binding_requires_exact_parent_and_committed_and_current_absence(tmp_path, monkeypatch, tamper):
    commit, blob = "a" * 40, "b" * 40
    source = "backend/quota.py"
    original = "LIMIT = 2\n"
    record = {"id": "remove-quota", "implementation_commit": commit, "reason": "quota removal", "review": "PR",
              "source_blobs": {source: blob}, "removed_bindings": [{"source": source, "symbol": "LIMIT",
              "before_ast": ast.dump(ast.parse(original).body[0], include_attributes=False)}]}
    if tamper == "untracked":
        record["source_blobs"] = {"backend/other.py": blob}
    path = tmp_path / changes.MANIFEST
    path.parent.mkdir()
    path.write_text(json.dumps({"schema_version": 1, "records": [record]}), encoding="utf-8")
    target = tmp_path / source
    target.parent.mkdir()
    target.write_text(original if tamper == "current" else "", encoding="utf-8")
    def git(args, **kwargs):
        if args[1] in ("log", "merge-base"):
            return b""
        if args[1] == "rev-parse":
            return blob.encode()
        assert args[1] == "show"
        if "^:" in args[2]:
            return ("LIMIT = 5\n" if tamper == "parent" else original).encode()
        return (original if tamper == "commit" else "").encode()
    monkeypatch.setattr(changes.subprocess, "check_output", git)
    if tamper:
        with pytest.raises(ValueError, match="removed binding"):
            changes.load(tmp_path)
    else:
        assert changes.removed_bindings(changes.load(tmp_path)) == {(source, "LIMIT")}
