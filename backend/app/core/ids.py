from __future__ import annotations

import secrets
import time
from uuid import UUID


def uuid7_string(*, timestamp_ms: int | None = None) -> str:
    """Return an RFC 9562 UUIDv7 string without requiring Python 3.14."""

    unix_ms = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    if not 0 <= unix_ms < 1 << 48:
        raise ValueError("timestamp_ms must fit in 48 bits")

    random_bits = secrets.randbits(74)
    random_a = random_bits >> 62
    random_b = random_bits & ((1 << 62) - 1)
    value = (
        (unix_ms << 80)
        | (0x7 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return str(UUID(int=value))
