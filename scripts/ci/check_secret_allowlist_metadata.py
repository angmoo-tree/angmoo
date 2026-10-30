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
EXPECTED_COUNT = 55
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
POSTGRESQL_ADOPTION_COMMIT = '6ff382a11f7db48278c83de9a9ce044954d7fced'
POSTGRESQL_ADOPTION_ENTRIES = {('.github/workflows/ci.yml', '76ba459eb6527951dab037a25c648a083558e0a6bd4e4475ad3314f3ae5b6ac1'): {'source_git_blob': '6e95cec5646cd05863d866b5b0ff0b46d3515300',
                                                                                                    'source_path': '.github/workflows/ci.yml'},
 ('backend/security/secret_scan_allowlist.json', '1c429e44bf84430c4f6fb0ee312f28f82fb0cc273fcd83b44f98173892812d28'): {'source_git_blob': '374e93d25db33eee15743afb07845a898c1d3509',
                                                                                                                       'source_path': 'launcher/migrate/docker_migrate.py'},
 ('backend/security/secret_scan_allowlist.json', '1edc9310fee4f3227ec5cebac21768eaaf31f45e388812ae4b4e00615947560c'): {'source_git_blob': '74a6f983bb07f11450a34863e29889e2de9dbcd2',
                                                                                                                       'source_path': 'scripts/release/postgresql_feature_smoke.py'},
 ('backend/security/secret_scan_allowlist.json', '66a4a36faab996610a0dd73afdb82d065f9d71da4fed066cb80be35621f94d4d'): {'source_git_blob': 'be33cf215e6eedb0dffc7dd30c66d6ce7a0fe112',
                                                                                                                       'source_path': 'scripts/docker/postgres-entrypoint.sh'},
 ('backend/security/secret_scan_allowlist.json', '6f1524fe282ecb4c8e68092a6669e7dd42a78a26768c5985f8d179640708ac81'): {'source_git_blob': '374e93d25db33eee15743afb07845a898c1d3509',
                                                                                                                       'source_path': 'launcher/migrate/docker_migrate.py'},
 ('backend/security/secret_scan_allowlist.json', '765e1bc80df1a15957d6dd1288e3a962b622a25cab47bbec7024ae63a8bc5333'): {'source_git_blob': 'be33cf215e6eedb0dffc7dd30c66d6ce7a0fe112',
                                                                                                                       'source_path': 'scripts/docker/postgres-entrypoint.sh'},
 ('backend/security/secret_scan_allowlist.json', '76ba459eb6527951dab037a25c648a083558e0a6bd4e4475ad3314f3ae5b6ac1'): {'source_git_blob': '6e95cec5646cd05863d866b5b0ff0b46d3515300',
                                                                                                                       'source_path': '.github/workflows/ci.yml'},
 ('backend/security/secret_scan_allowlist.json', '8ae7c35eda7736b6375895954576bc625aa5b52ca0862a06e3be0929003fc77b'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                       'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('backend/security/secret_scan_allowlist.json', 'aa82d37d6820ba9d40c4afb0ba7b4c83dca0e266d0924fb1debe7f4a31da393f'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                       'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('backend/security/secret_scan_allowlist.json', 'b4be8cfdb7631ba340f88f32c54944867488eddf92af39391ca69131710ef9a2'): {'source_git_blob': '7558172380914f297432e4f9b254fb367c398007',
                                                                                                                       'source_path': 'scripts/postgresql_experiment/prepare_phone_database.py'},
 ('backend/security/secret_scan_allowlist.json', 'c0dae2779e0cce67bc5fa24497bb5e699e4371cec71d9e33d0b5eacf40821359'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                       'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('backend/security/secret_scan_allowlist.json', 'ee8e07741e4b17eaceef5782c0dccbb2ae45f2591a7acd9f6f643557a8efe3c0'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                       'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('backend/security/secret_scan_allowlist.json', 'ff475bc505011d4141d043fcadf77bc31e608f4133d03534e78af897c066c625'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                       'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('backend/tests/postgresql/test_experience_upgrade_guard.py', '8ae7c35eda7736b6375895954576bc625aa5b52ca0862a06e3be0929003fc77b'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                                     'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('backend/tests/postgresql/test_experience_upgrade_guard.py', 'aa82d37d6820ba9d40c4afb0ba7b4c83dca0e266d0924fb1debe7f4a31da393f'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                                     'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('backend/tests/postgresql/test_experience_upgrade_guard.py', 'c0dae2779e0cce67bc5fa24497bb5e699e4371cec71d9e33d0b5eacf40821359'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                                     'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('backend/tests/postgresql/test_experience_upgrade_guard.py', 'ee8e07741e4b17eaceef5782c0dccbb2ae45f2591a7acd9f6f643557a8efe3c0'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                                     'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('backend/tests/postgresql/test_experience_upgrade_guard.py', 'ff475bc505011d4141d043fcadf77bc31e608f4133d03534e78af897c066c625'): {'source_git_blob': 'd2f56a778710d612f447f6453d9dacfc30e4a128',
                                                                                                                                     'source_path': 'backend/tests/postgresql/test_experience_upgrade_guard.py'},
 ('launcher/migrate/docker_migrate.py', '1c429e44bf84430c4f6fb0ee312f28f82fb0cc273fcd83b44f98173892812d28'): {'source_git_blob': '374e93d25db33eee15743afb07845a898c1d3509',
                                                                                                              'source_path': 'launcher/migrate/docker_migrate.py'},
 ('launcher/migrate/docker_migrate.py', '6f1524fe282ecb4c8e68092a6669e7dd42a78a26768c5985f8d179640708ac81'): {'source_git_blob': '374e93d25db33eee15743afb07845a898c1d3509',
                                                                                                              'source_path': 'launcher/migrate/docker_migrate.py'},
 ('scripts/docker/postgres-entrypoint.sh', '66a4a36faab996610a0dd73afdb82d065f9d71da4fed066cb80be35621f94d4d'): {'source_git_blob': 'be33cf215e6eedb0dffc7dd30c66d6ce7a0fe112',
                                                                                                                 'source_path': 'scripts/docker/postgres-entrypoint.sh'},
 ('scripts/docker/postgres-entrypoint.sh', '765e1bc80df1a15957d6dd1288e3a962b622a25cab47bbec7024ae63a8bc5333'): {'source_git_blob': 'be33cf215e6eedb0dffc7dd30c66d6ce7a0fe112',
                                                                                                                 'source_path': 'scripts/docker/postgres-entrypoint.sh'},
 ('scripts/postgresql_experiment/prepare_phone_database.py', 'b4be8cfdb7631ba340f88f32c54944867488eddf92af39391ca69131710ef9a2'): {'source_git_blob': '7558172380914f297432e4f9b254fb367c398007',
                                                                                                                                   'source_path': 'scripts/postgresql_experiment/prepare_phone_database.py'},
 ('scripts/release/postgresql_feature_smoke.py', '1edc9310fee4f3227ec5cebac21768eaaf31f45e388812ae4b4e00615947560c'): {'source_git_blob': '74a6f983bb07f11450a34863e29889e2de9dbcd2',
                                                                                                                       'source_path': 'scripts/release/postgresql_feature_smoke.py'}}

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
    postgresql_entries = set()
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
        if entry.get("review_kind") == "postgresql-adoption-noncredential.v1":
            value_hash = hashlib.sha256(str(entry.get("value", "")).encode()).hexdigest()
            key = (entry.get("path"), value_hash)
            expected = POSTGRESQL_ADOPTION_ENTRIES.get(key)
            postgresql_entries.add(key)
            reviewed, due = "2026-10-30", "2027-01-30"
            if (expected is None or entry.get("rule") != "credentialed-database-url"
                    or entry.get("source_commit") != POSTGRESQL_ADOPTION_COMMIT
                    or entry.get("value_sha256") != value_hash
                    or any(entry.get(field) != value for field, value in (expected or {}).items())):
                errors.append(f"{label} differs from reviewed PostgreSQL noncredential source evidence")
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
    if postgresql_entries != set(POSTGRESQL_ADOPTION_ENTRIES):
        errors.append("allowlist must retain exactly the reviewed PostgreSQL noncredential tuples")
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
