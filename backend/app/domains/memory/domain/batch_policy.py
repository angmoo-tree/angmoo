"""Code-owned daily scheduling and budgets for opt-in Memory selection."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domains.memory.domain.errors import MemoryValidationError
from app.domains.memory.domain.lifecycle import as_utc


MEMORY_BATCH_POLICY_VERSION = "memory-batch.v2"
MEMORY_SELECTION_VERSION = "memory-selection.v2"
MAX_SELECTION_CANDIDATES = 2
MAX_SELECTION_INPUT_CHARACTERS = 12_000
MAX_SELECTION_OUTPUT_TOKENS = 2_048
MAX_SELECTION_SUMMARY_CHARACTERS = 120
MAX_SELECTION_INPUT_UTF8_BYTES = 12_000
MAX_SELECTION_INPUT_TOKEN_BOUND = 16_384
SELECTION_TOKEN_SPECIAL_RESERVE = 512
MEMORY_SHUTDOWN_SECONDS = 30
MEMORY_FINALIZE_RESERVE_SECONDS = 5
MEMORY_PROVIDER_TIMEOUT_SECONDS = 30
MAX_BATCH_ATTEMPTS = 3
MEMORY_CONSENT_VERSION = "memory-selection-consent.v1"


def memory_token_upper_bound(text: str) -> int:
    """Offline normalized byte-token bound, not a native Gemini token count.

    Do not download tokenizers or call a paid/API tokenizer during shutdown.
    Count the complete prompt/schema, reserve special/control tokens, and
    record the provider's actual usage separately after the single call.
    """
    return (
        len(unicodedata.normalize("NFKC", text).encode("utf-8"))
        + SELECTION_TOKEN_SPECIAL_RESERVE
    )


def schedule_timezone(value: str) -> ZoneInfo:
    if not isinstance(value, str) or len(value) > 80:
        raise MemoryValidationError("memory_schedule_timezone_invalid")
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise MemoryValidationError("memory_schedule_timezone_invalid") from None


def schedule_time(value: str) -> time:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", value
    ):
        raise MemoryValidationError("memory_schedule_time_invalid")
    return time.fromisoformat(value)


def daily_slot(day: date, *, local_time: str, timezone: str) -> datetime:
    """First occurrence of an overlap; first valid minute after a DST gap."""

    zone = schedule_timezone(timezone)
    wall = datetime.combine(day, schedule_time(local_time))
    for minute in range(24 * 60 + 1):
        candidate = wall + timedelta(minutes=minute)
        instant = candidate.replace(tzinfo=zone, fold=0).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == candidate:
            return instant
    raise MemoryValidationError("memory_schedule_slot_invalid")


def next_daily_slot(
    *,
    after: datetime,
    local_time: str,
    timezone: str,
    last_consumed_date: date | None = None,
) -> datetime:
    """A saved past time starts tomorrow; consumed local dates never repeat."""

    now = as_utc(after)
    day = now.astimezone(schedule_timezone(timezone)).date()
    if last_consumed_date is not None and day <= last_consumed_date:
        day = last_consumed_date + timedelta(days=1)
    for _ in range(3):
        instant = daily_slot(day, local_time=local_time, timezone=timezone)
        if instant > now:
            return instant
        day += timedelta(days=1)
    raise MemoryValidationError("memory_schedule_slot_invalid")


def retry_delay(attempt: int) -> timedelta:
    return timedelta(seconds=min(300, 30 * 2 ** max(0, min(attempt - 1, 3))))
