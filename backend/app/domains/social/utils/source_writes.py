"""Deterministic request digest for canonical Social write replay."""
import json
from hashlib import sha256


def _request_hash(*, operation: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        {"operation": operation, **payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
