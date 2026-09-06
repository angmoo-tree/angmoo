"""Stable manual inbox source IDs and UTC instant normalization."""

from datetime import UTC, datetime

SOURCE_PREFIX = "manual-inbox:"


def source_id(candidate_id: str) -> str:
    return f"{SOURCE_PREFIX}{candidate_id}"


def candidate_id(value: str) -> str | None:
    if not value.startswith(SOURCE_PREFIX):
        return None
    result = value[len(SOURCE_PREFIX) :].strip()
    return result or None


def is_manual_inbox_source(value: str) -> bool:
    return candidate_id(value) is not None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
