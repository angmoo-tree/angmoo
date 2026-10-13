"""Validate review metadata without printing exact allowlisted values."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "backend/security/secret_scan_allowlist.json"
REQUIRED_FIELDS = {
    "path",
    "rule",
    "value",
    "owner",
    "reason",
    "scope",
    "last_reviewed",
    "review_due",
    "removal_condition",
}
EXPECTED_COUNT = 31
PR365_CANARY_SHA256 = "aca32a5f456daa79bae5dfc7d0110a3bd19f8a9172bffe6f4d7d5365cad9d79c"
PR365_CANARY_PATHS = frozenset({
    "backend/tests/test_t2_secret_allowlist.py",
    "security/refactor_backend_additions.json",
    "security/post_refactor_contract_changes.json",
    "backend/security/secret_scan_allowlist.json",
})
PR365_CANARY_EVIDENCE = {
    "evidence_commit": "b19eca0196f92f7d48bf258df5ea3c466a1767c8",
    "evidence_path": "backend/tests/test_t2_secret_allowlist.py",
    "evidence_test": "test_pr365_noncredential_allowlists_never_hide_other_values_paths_or_rules",
    "evidence_git_blob": "05f9d788ddaa1d35b6cf6647668121fc1eba1881",
    "value_sha256": PR365_CANARY_SHA256,
}
EXPECTED_LAST_REVIEWED = "2026-08-14"
EXPECTED_REVIEW_DUE = "2026-11-14"
CHECKPOINT_PATH = "security/refactor_backend_checkpoint.json"
CHECKPOINT_FIXTURE_SHA256 = "6101ea509bfb6d2107fbd82e0d54fad69b0b440996f0b64fc93977eff3bb4131"
RESTORED_HISTORY_PATH = "backend/tests/test_langgraph_resident_engine.py"
ADDITIONS_PATH = "security/refactor_backend_additions.json"
ADDITIONS_TEST_PATH = "tests/integrations/test_direct_llm.py"
CHECKPOINT_EVIDENCE = {
    "rule": "google-api-key",
    "evidence_commit": "d7037625a19071eb279ad2ea35c3ace6fe5b5289",
    "evidence_path": "backend/tests/test_langgraph_resident_engine.py",
    "evidence_test": "test_generate_json_records_postprocess_error_on_repaired_success",
    "checkpoint_git_blob": "a4ec6e0870d39a1afffa6357a5922f1b5c164219",
    "value_sha256": CHECKPOINT_FIXTURE_SHA256,
}


def validate(path: Path = DEFAULT_PATH) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("allowlist schema_version must remain scanner-compatible version 1")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return errors + ["allowlist entries must be an array"]
    if len(entries) != EXPECTED_COUNT:
        errors.append(f"allowlist must contain exactly {EXPECTED_COUNT} tuples")
    seen: set[tuple[str, str, str]] = set()
    checkpoint_entries = 0
    restored_history_entries = 0
    additions_entries = 0
    canary_paths = set()
    for index, entry in enumerate(entries):
        label = f"entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            errors.append(f"{label} missing metadata fields: {sorted(missing)}")
        for field in REQUIRED_FIELDS:
            if not isinstance(entry.get(field), str) or not entry.get(field, "").strip():
                errors.append(f"{label}.{field} must be a non-empty string")
        tuple_key = (
            str(entry.get("path", "")),
            str(entry.get("rule", "")),
            str(entry.get("value", "")),
        )
        if tuple_key in seen:
            errors.append(f"{label} duplicates an exact tuple")
        seen.add(tuple_key)
        if entry.get("scope") != "exact path+rule+value tuple only":
            errors.append(f"{label}.scope must stay exact")
        reviewed, due = EXPECTED_LAST_REVIEWED, EXPECTED_REVIEW_DUE
        canary = entry.get("evidence_commit") == PR365_CANARY_EVIDENCE["evidence_commit"]
        if canary:
            canary_paths.add(entry.get("path"))
            reviewed, due = "2026-10-13", "2027-01-13"
            if entry.get("path") not in PR365_CANARY_PATHS or entry.get("rule") != "openai-api-key":
                errors.append(f"{label} is outside the exact reviewed PR365 canary scope")
            for field, expected in PR365_CANARY_EVIDENCE.items():
                if entry.get(field) != expected:
                    errors.append(f"{label}.{field} differs from the reviewed PR365 canary evidence")
            if hashlib.sha256(str(entry.get("value", "")).encode()).hexdigest() != PR365_CANARY_SHA256:
                errors.append(f"{label}.value differs from the reviewed noncredential test canary")
        if entry.get("path") == CHECKPOINT_PATH:
            checkpoint_entries += 1
            reviewed, due = "2026-09-05", "2026-12-05"
            for field, expected in CHECKPOINT_EVIDENCE.items():
                if entry.get(field) != expected:
                    errors.append(f"{label}.{field} differs from reviewed checkpoint fixture evidence")
            if hashlib.sha256(str(entry.get("value", "")).encode()).hexdigest() != CHECKPOINT_FIXTURE_SHA256:
                errors.append(f"{label}.value differs from the exact reviewed synthetic fixture")
        if entry.get("path") == RESTORED_HISTORY_PATH:
            restored_history_entries += 1
            if entry.get("rule") != "google-api-key":
                errors.append(f"{label}.rule differs from the reviewed historical fixture")
            if hashlib.sha256(str(entry.get("value", "")).encode()).hexdigest() != CHECKPOINT_FIXTURE_SHA256:
                errors.append(f"{label}.value differs from the exact reviewed historical fixture")
        if entry.get("path") == ADDITIONS_PATH and not canary:
            additions_entries += 1
            reviewed, due = "2026-09-28", "2026-12-28"
            for field, expected in CHECKPOINT_EVIDENCE.items():
                if entry.get(field) != expected:
                    errors.append(f"{label}.{field} differs from reviewed additive fixture evidence")
            if hashlib.sha256(str(entry.get("value", "")).encode()).hexdigest() != CHECKPOINT_FIXTURE_SHA256:
                errors.append(f"{label}.value differs from the exact reviewed additive fixture")
            additions = json.loads((ROOT / ADDITIONS_PATH).read_text(encoding="utf-8"))
            assertions = [assertion for record in additions["records"]
                          for assertion in record.get("test_assertions", {}).get(ADDITIONS_TEST_PATH, {}).get(CHECKPOINT_EVIDENCE["evidence_test"], [])]
            if not any(str(entry.get("value", "")) in assertion for assertion in assertions):
                errors.append("additive fixture exception requires the existing exact assertion evidence")
        if entry.get("last_reviewed") != reviewed:
            errors.append(f"{label}.last_reviewed differs from its recorded review date")
        if entry.get("review_due") != due:
            errors.append(f"{label}.review_due differs from its recorded review due date")
        for field in ("last_reviewed", "review_due"):
            try:
                date.fromisoformat(str(entry.get(field, "")))
            except ValueError:
                errors.append(f"{label}.{field} must be an ISO date")
    if checkpoint_entries != 1:
        errors.append("allowlist must contain exactly one reviewed checkpoint fixture tuple")
    if restored_history_entries != 1:
        errors.append("allowlist must contain exactly one reviewed historical fixture tuple")
    if additions_entries != 1:
        errors.append("allowlist must contain exactly one reviewed additive fixture tuple")
    if canary_paths != PR365_CANARY_PATHS:
        errors.append("allowlist must retain exactly the four reviewed PR365 canary paths")
    return errors


def main() -> int:
    try:
        errors = validate()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Secret allowlist metadata check failed: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"Secret allowlist metadata check passed: exact_tuples={EXPECTED_COUNT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
