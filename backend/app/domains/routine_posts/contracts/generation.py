"""Validated generation value and the provider seam used by runtime/fakes."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
from app.domains.routine_posts import schemas
from app.domains.routine_posts.contracts.context import RoutinePostContext


@dataclass(frozen=True)
class RoutineGeneration:
    plan: schemas.RoutineBeatPlan
    draft: schemas.RoutinePostDraft
    state_after: dict[str, object]


class RoutinePostProvider(Protocol):
    async def generate(
        self,
        *,
        resident_context: Any,
        routine_context: RoutinePostContext,
        beat: Any,
        tracker: Any,
    ) -> RoutineGeneration: ...
