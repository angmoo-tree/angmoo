"""Common UTC normalization for API response timestamps."""
from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, field_validator


def normalize_utc_instant(value: Any) -> Any:
    """Restore the canonical UTC offset SQLite cannot persist."""

    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

class UtcInstantResponseModel(BaseModel):
    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def normalize_datetime_fields(cls, value: Any) -> Any:
        return normalize_utc_instant(value)
