"""Deterministic text codecs used by the embedded canonical store."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
import json
import math
import re
from typing import Any, Iterable
from uuid import UUID


_ULID_PATTERN = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")


def encode_uuid_text(value: UUID | str) -> str:
    """Return the canonical lower-case, hyphenated UUID representation."""

    return str(UUID(str(value)))


def encode_ulid_text(value: str) -> str:
    """Return the canonical upper-case Crockford ULID representation."""

    normalized = value.strip().upper()
    if not _ULID_PATTERN.fullmatch(normalized):
        raise ValueError("invalid ULID text")
    return normalized


def encode_utc_timestamp(value: datetime) -> str:
    """Serialize an aware timestamp as a fixed UTC ISO-8601 value."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("canonical timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def decode_utc_timestamp(value: str) -> datetime:
    """Parse canonical UTC text and reject non-UTC or naive values."""

    if not value.endswith("Z"):
        raise ValueError("canonical timestamps must use the UTC Z suffix")
    parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("canonical timestamps must include an offset")
    return parsed.astimezone(UTC)


def encode_json_document(value: Any) -> str:
    """Serialize JSON deterministically without ASCII escaping or NaN values."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_json_document(value: str) -> Any:
    return json.loads(value)


def encode_enum_value(value: Enum | str, *, allowed: Iterable[str]) -> str:
    """Normalize an enum/string and enforce the schema's explicit value set."""

    normalized = str(value.value if isinstance(value, Enum) else value)
    allowed_values = frozenset(allowed)
    if normalized not in allowed_values:
        raise ValueError(f"unsupported enum value: {normalized}")
    return normalized


def encode_vector_json(values: Iterable[float]) -> str:
    """Stable JSON fallback for legacy pgvector payloads during migration."""

    normalized = [float(value) for value in values]
    if any(not math.isfinite(value) for value in normalized):
        raise ValueError("vector values must be finite")
    return encode_json_document(normalized)


__all__ = [
    "decode_json_document",
    "decode_utc_timestamp",
    "encode_enum_value",
    "encode_json_document",
    "encode_ulid_text",
    "encode_utc_timestamp",
    "encode_uuid_text",
    "encode_vector_json",
]
