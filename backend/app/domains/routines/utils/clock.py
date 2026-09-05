from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.domains.routines.contracts.clock import Clock


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


def resolve_clock(*, now: datetime | None, clock: Clock | None) -> Clock:
    if now is not None and clock is not None:
        raise ValueError("now_and_clock_are_mutually_exclusive")
    if now is not None:
        return FrozenClock(now)
    return clock or SystemClock()



__all__ = ["FrozenClock", "SystemClock", "resolve_clock"]
