from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domains.routines.contracts.clock import Clock
from app.domains.routines.ports.daily_plan_repository import DailyPlanRepository


@dataclass(frozen=True)
class PrepareDailyPlan:
    repository: DailyPlanRepository
    clock: Clock

    def __call__(
        self, *, character_id: str, world_id: str, user: Any, data: Any
    ) -> Any:
        return self.repository.prepare(
            character_id=character_id,
            world_id=world_id,
            user=user,
            data=data,
            now=self.clock.now_utc(),
        )


@dataclass(frozen=True)
class GetDailyPlan:
    repository: DailyPlanRepository
    clock: Clock

    def __call__(self, *, character_id: str, world_id: str, user: Any) -> Any:
        return self.repository.get(
            character_id=character_id,
            world_id=world_id,
            user=user,
            now=self.clock.now_utc(),
        )


@dataclass(frozen=True)
class UpdateRuntimeMode:
    repository: DailyPlanRepository
    clock: Clock

    def __call__(
        self, *, character_id: str, world_id: str, user: Any, data: Any
    ) -> Any:
        return self.repository.update_runtime_mode(
            character_id=character_id,
            world_id=world_id,
            user=user,
            data=data,
            now=self.clock.now_utc(),
        )


__all__ = ["GetDailyPlan", "PrepareDailyPlan", "UpdateRuntimeMode"]
