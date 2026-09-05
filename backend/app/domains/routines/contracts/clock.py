from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class ClockPort(Protocol):
    """Return one aware UTC instant for a use-case invocation."""

    def now_utc(self) -> datetime: ...


Clock = ClockPort

__all__ = ["Clock", "ClockPort"]
