from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Return one aware UTC instant for a use-case invocation."""

    def now_utc(self) -> datetime: ...


__all__ = ["Clock"]
