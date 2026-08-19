from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True)
class FrozenClock:
    instant: datetime

    def now_utc(self) -> datetime:
        if self.instant.tzinfo is None:
            return self.instant.replace(tzinfo=UTC)
        return self.instant.astimezone(UTC)


__all__ = ["FrozenClock", "SystemClock"]
