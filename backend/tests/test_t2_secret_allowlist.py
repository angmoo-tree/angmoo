from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import pytest


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


def test_checkpoint_exception_matches_only_the_existing_frozen_synthetic_fixture() -> None:
    payload = json.loads(checker.DEFAULT_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in payload["entries"] if item["path"] == checker.CHECKPOINT_PATH)
    original = next(item for item in payload["entries"] if item["path"] == checker.CHECKPOINT_EVIDENCE["evidence_path"] and item["rule"] == entry["rule"])
    assert entry["value"] == original["value"]
    assert hashlib.sha256(entry["value"].encode()).hexdigest() == checker.CHECKPOINT_FIXTURE_SHA256
    checkpoint_bytes = (REPO_ROOT / checker.CHECKPOINT_PATH).read_bytes().replace(b"\r\n", b"\n")
    checkpoint = json.loads(checkpoint_bytes)
    source_path = entry["evidence_path"].removeprefix("backend/")
    assertions = checkpoint["test_assertions"][source_path][entry["evidence_test"]]
    assert any(entry["value"] in assertion for assertion in assertions)
    assert checkpoint["commit"] == entry["evidence_commit"]
    assert hashlib.sha1(f"blob {len(checkpoint_bytes)}\0".encode() + checkpoint_bytes).hexdigest() == entry["checkpoint_git_blob"]


@pytest.mark.parametrize("field,replacement", [
    ("path", "security/*"),
    ("rule", "openai-api-key"),
    ("value", "different-fixture-value"),
    ("value_sha256", "0" * 64),
    ("checkpoint_git_blob", "0" * 40),
    ("evidence_commit", "0" * 40),
])
def test_checkpoint_exception_cannot_expand_or_change_its_exact_evidence(tmp_path: Path, field: str, replacement: str) -> None:
    payload = json.loads(checker.DEFAULT_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in payload["entries"] if item["path"] == checker.CHECKPOINT_PATH)
    entry[field] = replacement
    fixture = tmp_path / "allowlist.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    assert checker.validate(fixture)


def test_checkpoint_exception_does_not_suppress_another_value_path_or_rule() -> None:
    scanner_spec = importlib.util.spec_from_file_location("checkpoint_fixture_scanner", REPO_ROOT / "scripts/security_secret_scan.py")
    scanner = importlib.util.module_from_spec(scanner_spec)
    sys.modules[scanner_spec.name] = scanner
    scanner_spec.loader.exec_module(scanner)
    allowlist = scanner.load_allowlist(checker.DEFAULT_PATH)
    entry = next(item for item in allowlist if item.path == checker.CHECKPOINT_PATH)
    assert list(scanner.scan_text(entry.path, entry.value, allowlist=allowlist)) == []
    assert {finding.rule for finding in scanner.scan_text("security/another-checkpoint.json", entry.value, allowlist=allowlist)} == {"google-api-key"}
    assert {finding.rule for finding in scanner.scan_text(entry.path, entry.value + "1", allowlist=allowlist)} == {"google-api-key"}
    another_rule = next(item for item in allowlist if item.path == "backend/tests/test_security_secret_scan.py" and item.rule == "openai-api-key")
    assert {finding.rule for finding in scanner.scan_text(entry.path, another_rule.value, allowlist=allowlist)} == {"openai-api-key"}
