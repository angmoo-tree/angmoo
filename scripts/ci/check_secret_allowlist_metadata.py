"""Validate review metadata without printing exact allowlisted values."""

from __future__ import annotations

from datetime import date
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
EXPECTED_COUNT = 23
EXPECTED_LAST_REVIEWED = "2026-08-14"
EXPECTED_REVIEW_DUE = "2026-11-14"


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
        if entry.get("last_reviewed") != EXPECTED_LAST_REVIEWED:
            errors.append(f"{label}.last_reviewed is not the T2 review date")
        if entry.get("review_due") != EXPECTED_REVIEW_DUE:
            errors.append(f"{label}.review_due is not the T2 review due date")
        for field in ("last_reviewed", "review_due"):
            try:
                date.fromisoformat(str(entry.get(field, "")))
            except ValueError:
                errors.append(f"{label}.{field} must be an ISO date")
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
