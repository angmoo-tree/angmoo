from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts/ci/check_secret_allowlist_metadata.py"
SPEC = importlib.util.spec_from_file_location("angmoo_t2_allowlist", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_current_exact_allowlist_metadata_passes() -> None:
    assert checker.validate() == []


def test_broad_scope_and_missing_review_metadata_are_rejected(tmp_path: Path) -> None:
    payload = json.loads(checker.DEFAULT_PATH.read_text(encoding="utf-8"))
    payload["entries"][0]["scope"] = "all files"
    del payload["entries"][1]["review_due"]
    fixture = tmp_path / "allowlist.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    errors = checker.validate(fixture)

    assert any("scope must stay exact" in error for error in errors)
    assert any("missing metadata fields" in error for error in errors)
