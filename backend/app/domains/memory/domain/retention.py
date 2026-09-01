"""Deterministic retention and pin policy."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domains.memory.domain.errors import MemoryValidationError


DEFAULT_MEMORY_RETENTION_DAYS = 180
MIN_MEMORY_RETENTION_DAYS = 1
MAX_MEMORY_RETENTION_DAYS = 3650


def validate_retention_days(value: int) -> int:
    if not MIN_MEMORY_RETENTION_DAYS <= value <= MAX_MEMORY_RETENTION_DAYS:
        raise MemoryValidationError("memory_retention_days_invalid")
    return value


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_memory_expired(
    *,
    valid_until: datetime | None,
    pinned_at: datetime | None,
    now: datetime,
) -> bool:
    """Pinned rows remain live until explicit deletion or supersession."""

    if pinned_at is not None or valid_until is None:
        return False
    return _aware_utc(valid_until) <= _aware_utc(now)


__all__ = [
    "DEFAULT_MEMORY_RETENTION_DAYS",
    "MAX_MEMORY_RETENTION_DAYS",
    "MIN_MEMORY_RETENTION_DAYS",
    "is_memory_expired",
    "validate_retention_days",
]
