"""A retirement record cannot bypass source, ownership or import preservation."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("sns_retirement_gate", ROOT / "scripts/ci/sns_execution_retirement.py")
gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
SOURCE = "backend/app/runtime/resident/langgraph.py"
OWNER = "backend/app/runtime/social/planned_actions.py"
BEFORE = "def shared(value): return value\ndef exclusive_graph(): return None\n"
AFTER = "def shared(value): return value\n"


@pytest.fixture
def evidence(tmp_path):
    owner = tmp_path / OWNER; owner.parent.mkdir(parents=True); owner.write_text(AFTER)
    tests = tmp_path / "backend/tests/current.py"; tests.parent.mkdir(parents=True)
    tests.write_text("def test_behavior(): assert 1 == 1\n")
    old = gate.definitions(BEFORE); new = gate.definitions(AFTER)
    record = {"implementation_commit": "b"*40, "source_blobs": {OWNER: "c"*40}, "retired_sns_modules": [{
        "source": SOURCE, "before_blob": "a"*40, "retired_symbols": ["exclusive_graph"],
        "moved_symbols": {"shared": {"source": OWNER, "symbol": "shared", "before_ast": old["shared"], "after_ast": new["shared"]}},
        "successor_tests": ["tests/current.py::test_behavior"]}]}
    def reader(*args, **kwargs):
        if args[0] == "rev-parse": return ("a"*40).encode()
        if args[0] == "ls-tree": return b""
        if args[0] == "show": return (BEFORE if "^:" in args[1] else AFTER).encode()
        pytest.fail("unexpected Git request")
    return tmp_path, record, reader


def test_closed_retirement_accounts_for_removed_and_retained_symbols(evidence):
    root, record, reader = evidence
    removed, modules = gate.validate([record], root=root, reader=reader)
    assert removed == {(SOURCE, "exclusive_graph")} and modules == {SOURCE}


@pytest.mark.parametrize("damage", ["restored_source", "preimage", "missing_symbol", "changed_owner", "missing_test", "suppressed_test", "unsupported_module", "still_committed"])
def test_retirement_rejects_each_unproven_source_or_behavior_delta(evidence, damage):
    root, record, reader = evidence
    item = record["retired_sns_modules"][0]
    if damage == "restored_source":
        path = root / SOURCE; path.parent.mkdir(parents=True); path.write_text(BEFORE)
    elif damage == "preimage": item["before_blob"] = "0"*40
    elif damage == "missing_symbol": item["retired_symbols"] = []
    elif damage == "changed_owner": (root/OWNER).write_text("def shared(value): return None\n")
    elif damage == "missing_test": item["successor_tests"] = ["tests/current.py::missing"]
    elif damage == "suppressed_test": (root/"backend/tests/current.py").write_text("@pytest.mark.skip\ndef test_behavior(): assert 1 == 1\n")
    elif damage == "unsupported_module": item["source"] = "backend/app/runtime/other.py"
    else:
        original = reader
        reader = lambda *a, **k: b"still tracked" if a[0] == "ls-tree" else original(*a, **k)
    with pytest.raises(ValueError): gate.validate([record], root=root, reader=reader)


@pytest.mark.parametrize("source", [
    "from app.runtime.resident import langgraph\n",
    "import app.runtime.resident.langgraph\n",
    "def resume():\n    from .resident.langgraph import run_resident_langgraph\n",
    "import importlib\ndef resume(): return importlib.import_module('app.runtime.resident.langgraph')\n",
])
def test_retirement_rejects_global_local_relative_and_dynamic_old_imports(evidence, source):
    root, record, reader = evidence
    path = root/"backend/app/runtime/gateway.py"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(source)
    with pytest.raises(ValueError, match="import"): gate.validate([record], root=root, reader=reader)


@pytest.mark.parametrize("damage", ["none", "unproven", "remaining_source", "changed_owner"])
def test_committed_source_requires_exact_closed_retirement(evidence, monkeypatch, damage):
    root, record, reader = evidence
    monkeypatch.syspath_prepend(str(ROOT / "scripts/ci"))
    spec = importlib.util.spec_from_file_location("sns_preservation_owned", ROOT / "scripts/ci/check_refactor_preservation.py")
    preservation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preservation)
    arbitrary = "backend/app/current_unrecorded.py"
    def committed_reader(*args, **kwargs):
        if args[0] == "log":
            return (SOURCE + "\n" + arbitrary + "\n").encode()
        return reader(*args, **kwargs)
    monkeypatch.setattr(preservation, "git_bytes", committed_reader)
    if damage == "remaining_source":
        path = root / SOURCE
        path.parent.mkdir(parents=True)
        path.write_text(BEFORE)
    elif damage == "changed_owner":
        (root / OWNER).write_text("def shared(value): return None\n")
    if damage in {"remaining_source", "changed_owner"}:
        with pytest.raises(ValueError):
            preservation.unrecorded_committed_sources({"commit": "d"*40}, [], {}, root,
                                                      approved_changes=[record])
    else:
        errors = preservation.unrecorded_committed_sources({"commit": "d"*40}, [], {}, root,
            approved_changes=[] if damage == "unproven" else [record])
        assert errors == ["committed source lacks append-only introduction evidence: " + path
                          for path in sorted({arbitrary, SOURCE} if damage == "unproven" else {arbitrary})]


@pytest.fixture
def reviewed_owner_change(evidence):
    root, retirement, original_reader = evidence
    retirement.update(id="retirement", reason="closed retirement", review="owned behavior reviewed")
    updated = "def shared(value): return value + 1\n"
    change = {"id": "owner-change", "implementation_commit": "d"*40,
        "reason": "reviewed owner behavior change", "review": "approved exact regression",
        "source_blobs": {OWNER: "e"*40}, "definitions": [{"source": OWNER, "symbol": "shared",
            "before_ast": gate.definitions(AFTER)["shared"], "after_ast": gate.definitions(updated)["shared"]}]}
    records = [retirement, change]
    (root / OWNER).write_text(updated)
    manifest = root / "security/post_refactor_contract_changes.json"
    manifest.parent.mkdir()
    def save():
        manifest.write_text(json.dumps({"schema_version": 1, "records": records}))
    save()
    def reader(*args, **kwargs):
        if args[0] in {"log", "merge-base"}: return b""
        if args == ("rev-parse", "b"*40 + ":" + OWNER): return ("c"*40).encode()
        if args == ("rev-parse", "d"*40 + ":" + OWNER): return ("e"*40).encode()
        if args == ("show", "d"*40 + "^:" + OWNER): return AFTER.encode()
        if args == ("show", "d"*40 + ":" + OWNER): return updated.encode()
        return original_reader(*args, **kwargs)
    return root, records, reader, save


def test_retained_owner_accepts_only_verified_continuous_committed_change(reviewed_owner_change):
    root, records, reader, _ = reviewed_owner_change
    removed, modules = gate.validate(records, root=root, reader=reader)
    assert removed == {(SOURCE, "exclusive_graph")} and modules == {SOURCE}
    assert records[0]["retired_sns_modules"][0]["moved_symbols"]["shared"]["after_ast"] == gate.definitions(AFTER)["shared"]


@pytest.mark.parametrize("damage", ["no_record", "wrong_symbol", "broken_chain", "uncommitted_working_tree"])
def test_retained_owner_rejects_unreviewed_or_discontinuous_change(reviewed_owner_change, damage):
    root, records, reader, save = reviewed_owner_change
    if damage == "no_record": records.pop()
    elif damage == "wrong_symbol": records[1]["definitions"][0]["symbol"] = "different"
    elif damage == "broken_chain": records[1]["definitions"][0]["before_ast"] = gate.definitions("def shared(value): return 0\n")["shared"]
    else: (root / OWNER).write_text("def shared(value): return value + 2\n")
    save()
    with pytest.raises(ValueError): gate.validate(records, root=root, reader=reader)


@pytest.mark.parametrize("damage", ["blob", "before", "after"])
def test_retained_owner_rejects_forged_committed_provenance(reviewed_owner_change, damage):
    root, records, reader, save = reviewed_owner_change
    if damage == "blob": records[1]["source_blobs"][OWNER] = "f"*40
    else: records[1]["definitions"][0][damage + "_ast"] = gate.definitions("def shared(value): return None\n")["shared"]
    save()
    with pytest.raises(ValueError, match="provenance|preimage"):
        gate.validate(records, root=root, reader=reader)


def test_retained_owner_cannot_rewrite_the_frozen_retirement_definition(reviewed_owner_change):
    root, records, reader, save = reviewed_owner_change
    records[0]["retired_sns_modules"][0]["moved_symbols"]["shared"]["after_ast"] = records[1]["definitions"][0]["after_ast"]
    save()
    with pytest.raises(ValueError, match="reviewed ownership"):
        gate.validate(records, root=root, reader=reader)


def test_retained_owner_rejects_committed_change_after_an_unreviewed_gap(reviewed_owner_change):
    root, records, reader, save = reviewed_owner_change
    gap = "def shared(value): return 0\n"
    records[1]["definitions"][0]["before_ast"] = gate.definitions(gap)["shared"]
    save()
    def committed_gap_reader(*args, **kwargs):
        if args == ("show", "d"*40 + "^:" + OWNER): return gap.encode()
        return reader(*args, **kwargs)
    # Provenance is valid, but the frozen owner cannot reach the new definition
    # through this record because the intervening change was never reviewed.
    with pytest.raises(ValueError, match="reviewed ownership"):
        gate.validate(records, root=root, reader=committed_gap_reader)


def test_retained_owner_rejects_committed_delta_for_a_different_owner(reviewed_owner_change):
    root, records, reader, save = reviewed_owner_change
    other = "backend/app/runtime/social/other_owner.py"
    records[1]["source_blobs"] = {other: "e"*40}
    records[1]["definitions"][0]["source"] = other
    save()
    def other_owner_reader(*args, **kwargs):
        mapped = tuple(arg.replace(other, OWNER) for arg in args)
        return reader(*mapped, **kwargs)
    with pytest.raises(ValueError, match="reviewed ownership"):
        gate.validate(records, root=root, reader=other_owner_reader)
