"""Verify M4 private/public API and resident contracts without network access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app as private_app  # noqa: E402
from app.public_main import app as public_app  # noqa: E402
from app.services.langgraph_resident import _ResidentGraphState  # noqa: E402


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
EXPECTED_PRIVATE_OPENAPI_SHA256 = (
    "86A727172D133F4AAC680F8C4ECA514E5FE0CABD15F9FDF47614B5FB308B4BF4"
)
EXPECTED_PUBLIC_OPENAPI_SHA256 = (
    "A4B7FEB31B3E3633D9A74AC9F524E869DE7A5CEFCD5228227853305A19412681"
)
EXPECTED_CREDENTIAL_SHA256 = (
    "E3CDE9603CA664FC59C285B3401A53A569E6AE4A1C2E778E03E37D71ADBE69C9"
)
EXPECTED_LANGGRAPH_SHA256 = (
    "2534B9B70FD4EBC6730902DBB2D17E6DBE623967FED7CD15B6E5EBCB4767CC16"
)


class ContractVerificationError(RuntimeError):
    pass


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _operations(document: dict) -> dict[tuple[str, str], dict]:
    return {
        (path, method): operation
        for path, item in document["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    }


def verify() -> dict[str, object]:
    private_source = (
        BACKEND_ROOT / "security" / "m4_private_export_policy.json"
    ).exists()
    private = private_app.openapi()
    public = public_app.openapi()
    private_operations = _operations(private)
    public_operations = _operations(public)
    removed = set(private_operations) - set(public_operations)
    added = set(public_operations) - set(private_operations)
    drift = {
        key
        for key, operation in public_operations.items()
        if private_operations.get(key) != operation
    }
    removed_prefixes = {
        "/api/v1/admin": 28,
        "/api/v1/agent-tools": 24,
        "/api/v1/maintenance": 1,
    }
    removed_counts = {
        prefix: sum(path.startswith(prefix) for path, _ in removed)
        for prefix in removed_prefixes
    }
    policy_removed = sorted(
        f"{method.upper()} {path}"
        for path, method in removed
        if not any(path.startswith(prefix) for prefix in removed_prefixes)
    )

    static_path = REPO_ROOT / "frontend" / "public" / "openapi.json"
    static = json.loads(static_path.read_text(encoding="utf-8"))
    static_operations = {
        (f"/api/v1{path}", method)
        for path, item in static["paths"].items()
        for method in item
        if method in HTTP_METHODS
    }
    generated_bot = {
        key for key in public_operations if key[0].startswith("/api/v1/bot/")
    }

    schemas = private["components"]["schemas"]
    credential = {
        name: schemas[name] for name in ("CredentialRead", "CredentialUpsert")
    }
    langgraph_keys = sorted(_ResidentGraphState.__annotations__)
    facts = {
        "source_profile": "private" if private_source else "public",
        "private_paths": len(private["paths"]),
        "private_operations": len(private_operations),
        "private_schemas": len(schemas),
        "private_openapi_sha256": _canonical_sha256(private),
        "public_paths": len(public["paths"]),
        "public_operations": len(public_operations),
        "public_schemas": len(public["components"]["schemas"]),
        "public_openapi_sha256": _canonical_sha256(public),
        "removed_operations": len(removed),
        "removed_counts": removed_counts,
        "policy_removed_operations": policy_removed,
        "added_operations": len(added),
        "shared_operation_drift": len(drift),
        "local_bot_paths": len(static["paths"]),
        "local_bot_operations": len(static_operations),
        "local_bot_missing_generated": len(static_operations - generated_bot),
        "local_bot_missing_static": len(generated_bot - static_operations),
        "local_bot_openapi_sha256": _canonical_sha256(static),
        "credential_schema_sha256": _canonical_sha256(credential),
        "langgraph_state_keys": len(langgraph_keys),
        "langgraph_state_sha256": _canonical_sha256(langgraph_keys),
    }
    common_expected = {
        "public_paths": 116,
        "public_operations": 144,
        "public_schemas": 165,
        "public_openapi_sha256": EXPECTED_PUBLIC_OPENAPI_SHA256,
        "local_bot_paths": 14,
        "local_bot_operations": 18,
        "local_bot_missing_generated": 0,
        "local_bot_missing_static": 0,
        "credential_schema_sha256": EXPECTED_CREDENTIAL_SHA256,
        "langgraph_state_keys": 36,
        "langgraph_state_sha256": EXPECTED_LANGGRAPH_SHA256,
    }
    if private_source:
        expected = {
            **common_expected,
            "source_profile": "private",
            "private_paths": 151,
            "private_operations": 180,
            "private_schemas": 181,
            "private_openapi_sha256": EXPECTED_PRIVATE_OPENAPI_SHA256,
            "removed_operations": 54,
            "removed_counts": removed_prefixes,
            "policy_removed_operations": ["POST /api/v1/auth/signup"],
            "added_operations": 0,
            "shared_operation_drift": 0,
        }
    else:
        expected = {
            **common_expected,
            "source_profile": "public",
            "private_paths": 116,
            "private_operations": 144,
            "private_schemas": 165,
            "private_openapi_sha256": EXPECTED_PUBLIC_OPENAPI_SHA256,
            "removed_operations": 0,
            "removed_counts": {prefix: 0 for prefix in removed_prefixes},
            "policy_removed_operations": [],
            "added_operations": 0,
            "shared_operation_drift": 0,
        }
    mismatches = {
        key: {"expected": value, "actual": facts.get(key)}
        for key, value in expected.items()
        if facts.get(key) != value
    }
    if mismatches:
        raise ContractVerificationError(
            json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
        )
    return facts


def main() -> int:
    try:
        facts = verify()
    except (OSError, KeyError, json.JSONDecodeError, ContractVerificationError) as exc:
        print(f"M4 contract verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(facts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
