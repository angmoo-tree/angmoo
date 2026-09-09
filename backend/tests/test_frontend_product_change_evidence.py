"""Product changes do not exempt unrelated browser assertions or lock drift."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "frontend_product_changes", Path(__file__).resolve().parents[2] / "scripts/ci/post_refactor_contract_changes.py"
)
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)


def test_frontend_exact_chain_rejects_unrecorded_file_content_and_missing_steps():
    path = "browser-tests/example.spec.ts"
    record = {"frontend_files": [{"source": path,
        "before_sha256": changes.text_digest("old\n"),
        "after_sha256": changes.text_digest("new\n")}]}
    assert changes.frontend_matches(path, "old\n", "new\r\n", [record])
    assert not changes.frontend_matches(path, "old\n", "weakened\n", [record])
    assert not changes.frontend_matches("browser-tests/other.spec.ts", "old\n", "new\n", [record])
    with pytest.raises(ValueError, match="chain preimage"):
        changes.frontend_matches(path, "different old\n", "new\n", [record])


@pytest.mark.parametrize("revision", ["parent", "commit"])
def test_frontend_metadata_requires_real_committed_before_and_after(tmp_path, revision):
    import json
    commit = "a" * 40
    source = "frontend/package.json"
    record = {"id": "dependency-patch", "implementation_commit": commit,
        "reason": "security patch", "review": "PR321", "source_blobs": {source: "b" * 40},
        "frontend_files": [{"source": source, "before_sha256": changes.text_digest("old"),
                            "after_sha256": changes.text_digest("new")}]}
    target = tmp_path / changes.MANIFEST
    target.parent.mkdir()
    target.write_text(json.dumps({"schema_version": 1, "records": [record]}))
    def reader(*args, root):
        if args[0] in {"log", "merge-base"}:
            return b""
        if args[0] == "rev-parse":
            return b"b" * 40
        if "^:" in args[1]:
            return b"tampered" if revision == "parent" else b"old"
        return b"tampered" if revision == "commit" else b"new"
    with pytest.raises(ValueError, match="committed preimage"):
        changes.load(tmp_path, reader=reader)
