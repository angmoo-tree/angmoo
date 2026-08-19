from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


class DailyPlanRepository(Protocol):
    def prepare(
        self,
        *,
        character_id: str,
        world_id: str,
        user: Any,
        data: Any,
        now: datetime,
    ) -> Any: ...

    def get(
        self,
        *,
        character_id: str,
        world_id: str,
        user: Any,
        now: datetime,
    ) -> Any: ...

    def update_runtime_mode(
        self,
        *,
        character_id: str,
        world_id: str,
        user: Any,
        data: Any,
        now: datetime,
    ) -> Any: ...


__all__ = ["DailyPlanRepository"]
