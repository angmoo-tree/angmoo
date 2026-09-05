from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("backend_preservation", ROOT / "scripts/ci/check_refactor_preservation.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def test_pr263_checkpoint_preserves_hotfix_regressions_beyond_pr258():
    baseline = json.loads(p.BASELINE.read_text(encoding="utf-8"))
    checkpoint = json.loads(p.CHECKPOINT.read_text(encoding="utf-8"))
    moves = json.loads(p.git_bytes("show", f"{p.CHECKPOINT_COMMIT}:security/refactor_path_map.json"))["test_nodes"]
    assert p.checkpoint_errors(checkpoint, p.BASELINE.read_bytes()) == []
    original = set(p.mapped_targets(baseline["test_nodes"], moves, nodes=True).values())
    added = set(checkpoint["test_nodes"]) - original
    hotfix = {node for node in added if "test_embedded_data_migration.py" in node or "test_p8_l_d_installer_upgrade_contract.py" in node}
    assert hotfix
    for deleted in hotfix:
        approved = sorted(set(baseline["test_nodes"]) | set(checkpoint["test_nodes"]))
        remaining = sorted(set(checkpoint["test_nodes"]) - {deleted})
        assert p.missing_nodes(approved, remaining, moves, node_snapshots=[baseline["test_nodes"], checkpoint["test_nodes"]]) == [deleted]


@pytest.mark.parametrize("field", ["test_nodes", "tracked_files", "contracts", "test_assertions", "test_suppressions"])
def test_checkpoint_cannot_be_recaptured_to_hide_a_regression(field):
    checkpoint = json.loads(p.CHECKPOINT.read_text(encoding="utf-8"))
    checkpoint[field] = [] if field == "test_nodes" else {}
    assert any("checkpoint mutated" in error for error in p.checkpoint_errors(checkpoint, p.BASELINE.read_bytes()))


def test_original_baseline_and_wrong_checkpoint_commit_are_rejected():
    checkpoint = json.loads(p.CHECKPOINT.read_text(encoding="utf-8"))
    checkpoint["commit"] = "0" * 40
    errors = p.checkpoint_errors(checkpoint, b"{}")
    assert any("exact PR263 commit" in error for error in errors)
    assert any("PR258 source baseline mutated" in error for error in errors)


def test_nodes_follow_second_move_and_count_checkpoint_lineage_once():
    assert p.missing_nodes(["old::test", "pilot::test", "hotfix::test"],
                           ["final::test", "hotfix::test", "new::test"],
                           {"old::test": "pilot::test", "pilot::test": "final::test"},
                           node_snapshots=[["old::test"], ["pilot::test", "hotfix::test"]]) == []


def test_move_cannot_swallow_an_independent_existing_destination():
    with pytest.raises(ValueError, match="independent cases cannot collapse"):
        p.missing_nodes(["tests/t.py::test_a", "tests/t.py::test_b"], ["tests/t.py::test_b"],
                        {"tests/t.py::test_a": "tests/t.py::test_b"})


@pytest.mark.parametrize("moves,match", [
    ({"unknown::test": "new::test"}, "absent from frozen"),
    ({"old::test": "middle::test", "middle::test": "old::test"}, "cyclic"),
    ({"old::test": "final::test", "second::test": "final::test"}, "one-to-one"),
    ({"old::test": "old::test"}, "cyclic"),
])
def test_unexplained_missing_renamed_or_merged_test_nodes_are_rejected(moves, match):
    with pytest.raises(ValueError, match=match):
        p.missing_nodes(["old::test", "second::test"], ["final::test"], moves)


def write(root: Path, path: str, source: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def snapshot(source: str, node: str = "tests/test_old.py::test_contract") -> dict:
    path, _ = p.node_function(node)
    return {"test_nodes": [node], "test_assertions": {path: p.assertion_contracts(source)}}


def test_moved_test_cannot_keep_its_name_and_delete_assertion_or_raises(tmp_path):
    source = "def test_contract():\n    assert suffix == '-schema-v9'\n    with pytest.raises(ValueError, match='collision'):\n        upgrade()\n"
    expected = snapshot(source)
    node = expected["test_nodes"][0]
    target = "tests/domain/test_new.py::test_contract"
    for changed in (
        "def test_contract():\n    pass\n",
        "def test_contract():\n    assert True\n    with pytest.raises(Exception):\n        upgrade()\n",
        "def test_contract():\n    assert suffix == '-schema-v9'\n    upgrade()\n",
    ):
        write(tmp_path, "backend/tests/domain/test_new.py", changed)
        assert any("expectation missing or changed" in error for error in p.check_assertions([expected], {node: target}, {}, tmp_path))


def test_assertions_inside_local_test_helpers_cannot_disappear(tmp_path):
    source = "def helper():\n    assert result == 42\ndef test_contract():\n    helper()\n"
    expected = snapshot(source)
    node = expected["test_nodes"][0]
    write(tmp_path, "backend/tests/test_old.py", source.replace("assert result == 42", "pass"))
    assert any("expectation missing or changed" in error for error in p.check_assertions([expected], {node: node}, {}, tmp_path))


@pytest.mark.parametrize("source", [
    "import pytest\n@pytest.mark.skip(reason='hide regression')\ndef test_contract():\n    assert result == 42\n",
    "import pytest\n@pytest.mark.skipif(True, reason='hide regression')\ndef test_contract():\n    assert result == 42\n",
    "import pytest\n@pytest.mark.xfail\ndef test_contract():\n    assert result == 42\n",
    "import pytest\ndef test_contract():\n    pytest.skip('hide regression')\n    assert result == 42\n",
    "import pytest\npytestmark = pytest.mark.skip(reason='hide module')\ndef test_contract():\n    assert result == 42\n",
])
def test_new_skip_or_xfail_cannot_hide_a_collected_regression(tmp_path, source):
    write(tmp_path, "backend/tests/test_old.py", source)
    expected = {"test_suppressions": {"tests/test_old.py": {}}}
    assert any("skip/xfail suppression changed" in error for error in p.check_suppressions([expected], {}, tmp_path))


def test_existing_skips_are_preserved_and_collection_hook_suppression_is_guarded(tmp_path):
    source = "import pytest\ndef pytest_collection_modifyitems(items):\n    for item in items:\n        item.add_marker(pytest.mark.skip(reason='existing'))\n"
    write(tmp_path, "backend/tests/conftest.py", source)
    expected = {"test_suppressions": {"tests/conftest.py": p.suppression_contracts(source)}}
    assert p.check_suppressions([expected], {}, tmp_path) == []
    write(tmp_path, "backend/tests/conftest.py", source.replace("existing", "different reason"))
    assert p.check_suppressions([expected], {}, tmp_path)


def test_assertions_accept_explicit_path_move_and_additional_checks(tmp_path):
    source = "def test_contract():\n    assert 'app.core.config' in imports\n    assert result == 42\n"
    expected = snapshot(source)
    node = expected["test_nodes"][0]
    target = "tests/config/test_new.py::test_contract"
    write(tmp_path, "backend/tests/config/test_new.py", source.replace("app.core.config", "app.config") + "    assert extra is True\n")
    assert p.check_assertions([expected], {node: target}, {"backend/app/core/config.py": "backend/app/config.py"}, tmp_path) == []
    assert p.check_assertions([expected], {node: target}, {}, tmp_path)


def test_unchanged_synthetic_legacy_path_fixture_survives_real_move_without_weakening_expectations(tmp_path):
    source = "def test_contract():\n    assert check({'backend/app/core/config.py': 'backend/app/config.py'}) == []\n"
    expected = snapshot(source)
    node = expected["test_nodes"][0]
    files = {"backend/app/core/config.py": "backend/app/config.py"}
    write(tmp_path, "backend/tests/test_old.py", source)
    assert p.check_assertions([expected], {node: node}, files, tmp_path) == []
    write(tmp_path, "backend/tests/test_old.py", source.replace("== []", "== ['changed behavior']"))
    assert any("expectation missing or changed" in error for error in p.check_assertions([expected], {node: node}, files, tmp_path))


def test_parameterized_nodes_preserve_the_underlying_class_assertions(tmp_path):
    source = "class TestMigration:\n    def test_contract(self):\n        assert result.success\n"
    expected = snapshot(source, "tests/test_old.py::TestMigration::test_contract[v8]")
    node = expected["test_nodes"][0]
    target = "tests/migration/test_new.py::TestMigration::test_contract[v8]"
    write(tmp_path, "backend/tests/migration/test_new.py", source)
    assert p.check_assertions([expected], {node: target}, {}, tmp_path) == []
    assert p.missing_nodes([node], [target.replace("[v8]", "[v9]")], {node: target}) == [target]


def test_missing_or_empty_marker_cannot_preserve_a_source_implementation(tmp_path):
    old, target = "backend/app/old.py", "backend/app/domain/__init__.py"
    write(tmp_path, target, '"""Package marker."""\n')
    assert any("empty package marker" in error for error in p.check_sources([old], {old: target}, tmp_path))
    assert any("source missing" in error for error in p.check_sources([old], {old: "backend/app/missing.py"}, tmp_path))
    with pytest.raises(ValueError, match="absent from frozen"):
        p.check_sources([old], {"backend/app/typo.py": target}, tmp_path)


def test_source_moves_follow_multiple_steps_and_reject_unsafe_destination(tmp_path):
    write(tmp_path, "backend/app/current.py", "VALUE = 1\n")
    assert p.check_sources(["backend/app/old.py"], {"backend/app/old.py": "backend/app/intermediate.py", "backend/app/intermediate.py": "backend/app/current.py"}, tmp_path) == []
    assert p.check_sources(["backend/app/old.py"], {"backend/app/old.py": "../outside.py"}, tmp_path)


def test_addition_records_require_commit_feature_and_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(p, "git_bytes", lambda *args, **kwargs: b"")
    checkpoint = {"commit": "a" * 40, "test_nodes": []}
    additions = {"schema_version": 1, "checkpoint_commit": checkpoint["commit"], "records": [{"commit": "HEAD"}]}
    assert any("exact introduction commit" in error for error in p.addition_errors(additions, checkpoint, tmp_path))


def test_addition_history_cannot_be_removed_or_rewritten(monkeypatch, tmp_path):
    checkpoint = {"commit": "a" * 40, "test_nodes": []}
    record = {"commit": "b" * 40, "feature_id": "G01", "reason": "Config regressions", "tracked_files": {}, "test_nodes": [], "test_assertions": {}}
    previous = {"records": [record]}

    def evidence(*args, **kwargs):
        if args[0] == "log":
            return b"historical-metadata-commit\n"
        if args[0] == "show":
            return json.dumps(previous).encode()
        return b""

    monkeypatch.setattr(p, "git_bytes", evidence)
    for records in ([], [{**record, "reason": "rewritten"}]):
        additions = {"schema_version": 1, "checkpoint_commit": checkpoint["commit"], "records": records}
        assert any("history was changed or removed" in error for error in p.addition_errors(additions, checkpoint, tmp_path))


def test_addition_commit_source_and_assertion_provenance_are_checked(monkeypatch, tmp_path):
    source = b"def test_new():\n    assert result == 42\n"
    checkpoint = {"commit": "a" * 40, "test_nodes": []}
    record = {"commit": "b" * 40, "feature_id": "G01", "reason": "Config regressions",
              "tracked_files": {"backend/tests/test_new.py": p.git_blob(source)},
              "test_nodes": ["tests/test_new.py::test_new"],
              "test_assertions": {"tests/test_new.py": p.assertion_contracts(source.decode())}}
    monkeypatch.setattr(p, "git_bytes", lambda *args, **kwargs: source if args[0] == "show" else (record["commit"] + "\n").encode() if args[0] == "log" and "--diff-filter=A" in args else b"")
    additions = {"schema_version": 1, "checkpoint_commit": checkpoint["commit"], "records": [record]}
    assert p.addition_errors(additions, checkpoint, tmp_path) == []
    changed = copy.deepcopy(additions)
    changed["records"][0]["tracked_files"]["backend/tests/test_new.py"] = "0" * 40
    changed["records"][0]["test_assertions"]["tests/test_new.py"]["test_new"] = ["assert True"]
    errors = p.addition_errors(changed, checkpoint, tmp_path)
    assert any("source provenance changed" in error for error in errors)
    assert any("assertion provenance changed" in error for error in errors)


def test_later_commit_cannot_claim_it_introduced_an_older_unrecorded_source(monkeypatch, tmp_path):
    source = b"VALUE = 1\n"
    checkpoint = {"commit": "a" * 40, "test_nodes": []}
    record = {"commit": "c" * 40, "feature_id": "G01", "reason": "Source addition",
              "tracked_files": {"backend/app/new.py": p.git_blob(source)}, "test_nodes": [], "test_assertions": {}}

    def evidence(*args, **kwargs):
        if args[0] == "show":
            return source
        if args[0] == "log" and "--diff-filter=A" in args:
            return (("b" * 40) + "\n").encode()
        return b""

    monkeypatch.setattr(p, "git_bytes", evidence)
    additions = {"schema_version": 1, "checkpoint_commit": checkpoint["commit"], "records": [record]}
    assert any("first introduction commit" in error for error in p.addition_errors(additions, checkpoint, tmp_path))


def test_new_committed_source_requires_record_and_mapped_destinations_are_not_new_work(monkeypatch, tmp_path):
    monkeypatch.setattr(p, "git_bytes", lambda *args, **kwargs: b"backend/app/new.py\nbackend/app/moved.py\n")
    checkpoint = {"commit": "a" * 40}
    targets = {"backend/app/old.py": "backend/app/moved.py"}
    assert p.unrecorded_committed_sources(checkpoint, [], targets, tmp_path) == ["committed source lacks append-only introduction evidence: backend/app/new.py"]
    assert p.unrecorded_committed_sources(checkpoint, [{"tracked_files": {"backend/app/new.py": "blob"}}], targets, tmp_path) == []


def test_capture_does_not_call_surviving_frozen_bridge_a_new_source(monkeypatch):
    monkeypatch.setitem(sys.modules, "check_refactor_preservation", p)
    capture_spec = importlib.util.spec_from_file_location("capture_backend_checkpoint", ROOT / "scripts/ci/capture_refactor_backend_checkpoint.py")
    capture = importlib.util.module_from_spec(capture_spec)
    capture_spec.loader.exec_module(capture)
    old = "frontend/src/shared/media/safe-media-url.ts"
    new = "frontend/src/lib/media/safe-media-url.ts"
    added = "backend/tests/test_new_regression.py"
    tracked = {old: "bridge-blob", new: "implementation-blob", added: "new-test-blob"}
    assert capture.unprotected_files(tracked, [old], {old: new}) == {added: "new-test-blob"}


def test_new_split_requires_real_symbols_consumers_and_behavior_test_evidence(monkeypatch, tmp_path):
    old = "backend/app/old.py"
    source = b"def read():\n    return 1\ndef write():\n    return 2\n"
    monkeypatch.setattr(p, "git_bytes", lambda *args, **kwargs: b'{"details": {}}' if args[0] == "show" else source)
    write(tmp_path, "backend/app/read.py", "def read():\n    return 1\n")
    write(tmp_path, "backend/app/write.py", "def write():\n    return 2\n")
    write(tmp_path, "backend/app/caller.py", "from app.read import read\nfrom app.write import write\n")
    write(tmp_path, "backend/tests/test_move.py", "def test_read_write():\n    assert read() == 1\n    assert write() == 2\n")
    detail = {"split_files": {old: ["backend/app/read.py", "backend/app/write.py"]},
              "split_symbols": [{"old": f"{old}::{name}", "new": f"backend/app/{name}.py::{name}",
                                 "direct_consumers": ["backend/app/caller.py"], "test_nodes": ["tests/test_move.py::test_read_write"]} for name in ("read", "write")]}
    snapshots = [{"tracked_files": {old: p.git_blob(source)}}]
    assert p.check_split_evidence({"details": {"AR-B2": detail}}, snapshots, tmp_path) == []
    broken = copy.deepcopy(detail)
    broken["split_symbols"].pop()
    assert any("split omits" in error for error in p.check_split_evidence({"details": {"AR-B2": broken}}, snapshots, tmp_path))
    broken = copy.deepcopy(detail)
    broken["split_symbols"][0]["new"] = "backend/app/read.py::unknown"
    assert any("does not define" in error for error in p.check_split_evidence({"details": {"AR-B2": broken}}, snapshots, tmp_path))
