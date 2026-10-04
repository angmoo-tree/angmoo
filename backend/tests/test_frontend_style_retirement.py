"""Retiring obsolete native chrome CSS must not exempt missing product stock."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("style_changes", Path(__file__).resolve().parents[2] / "scripts/ci/post_refactor_contract_changes.py")
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)


def test_style_retirement_accepts_only_the_recorded_source_and_exact_preimage():
    source = "frontend/src/shell/old-controls.module.css"
    record = {"retired_frontend_styles": [{"source": source, "before_sha256": changes.text_digest("old css")} ]}
    assert changes.frontend_style_retirement_matches(source, "old css", [record])
    assert not changes.frontend_style_retirement_matches(source, "unrecorded css", [record])
    assert not changes.frontend_style_retirement_matches("frontend/src/shell/other.module.css", "old css", [record])


@pytest.mark.parametrize("case", ["valid", "changed_preimage", "still_committed", "resurrected", "active_import", "missing_owner"])
def test_style_retirement_requires_committed_deletion_and_no_remaining_consumers(tmp_path, case):
    commit = "a" * 40
    source = "frontend/src/shell/old-controls.module.css"
    consumer = "frontend/src/shell/bridge.tsx"
    replacement = "frontend/src/shell/toolbar.tsx"
    record = {"id": "retire-native-chrome", "implementation_commit": commit, "reason": "normal OS caption", "review": "local contract C09", "source_blobs": {consumer: "b" * 40, replacement: "c" * 40}, "retired_frontend_styles": [{"source": source, "consumer": consumer, "replacement": replacement, "before_sha256": changes.text_digest("old css")} ]}
    if case == "missing_owner": del record["source_blobs"][replacement]
    target = tmp_path / changes.MANIFEST
    target.parent.mkdir(); target.write_text(json.dumps({"schema_version": 1, "records": [record]}))
    if case in {"resurrected", "active_import"}:
        file = tmp_path / (source if case == "resurrected" else consumer)
        file.parent.mkdir(parents=True); file.write_text("old css" if case == "resurrected" else "import './old-controls.module.css';")
    def reader(*args, root):
        if args[0] in {"log", "merge-base"}: return b""
        if args[0] == "rev-parse": return record["source_blobs"][args[1].split(":", 1)[1]].encode()
        if args[0] == "ls-tree": return b"still tracked" if case == "still_committed" else b""
        return b"tampered" if case == "changed_preimage" else b"old css"
    if case == "valid": assert changes.load(tmp_path, reader=reader) == [record]
    else:
        with pytest.raises(ValueError): changes.load(tmp_path, reader=reader)
