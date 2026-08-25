"""Deterministic canonical JSON and SHA-256 helpers for World Package v1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import unicodedata
from typing import Any

from pydantic import BaseModel


def _normalize_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize_json(value.model_dump(mode="json", exclude_none=False))
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON forbids NaN and Infinity")
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            canonical_key = unicodedata.normalize("NFC", key)
            if canonical_key in normalized:
                raise ValueError("canonical JSON keys collide after NFC normalization")
            normalized[canonical_key] = _normalize_json(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_normalize_json(item) for item in value]
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value with the frozen v1 rules."""

    normalized = _normalize_json(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_entry_index_digest(entries: Sequence[Any]) -> str:
    """Hash the canonical manifest entry index, excluding manifest itself."""

    index: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, BaseModel):
            payload = entry.model_dump(mode="json")
        elif isinstance(entry, Mapping):
            payload = dict(entry)
        else:
            raise TypeError("entry index items must be mappings or Pydantic models")
        path = payload.get("path")
        if path == "manifest.json":
            raise ValueError("manifest.json must not appear in its own entry index")
        index.append(
            {
                "bytes": payload["bytes"],
                "media_type": payload["media_type"],
                "path": path,
                "sha256": payload["sha256"],
            }
        )
    index.sort(key=lambda item: item["path"])
    return canonical_sha256(index)
