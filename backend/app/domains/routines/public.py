"""Stable public API for deterministic daily planning and lifecycle."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.domains.routines.application.daily_plan import (
    GetDailyPlan,
    PrepareDailyPlan,
    UpdateRuntimeMode,
)
from app.domains.routines.application.reconcile_lifecycle import (
    ReconcileElapsedRoutines,
    RecoverExpiredRoutineClaims,
)
from app.domains.routines.domain.lifecycle import (
    ActivityRuntimeConflictError,
    ActivityRuntimeError,
    ActivityRuntimeNotFoundError,
    ActivityRuntimeValidationError,
    DaypartTransitionCounts,
    DueTick,
    RecoveryCounts,
    WorldInterruptionCounts,
    latest_due_tick,
)
from app.domains.routines.infrastructure.sqlalchemy_daily_activity_plans import (
    DAYPARTS,
    DAYPART_START_HOURS,
    EVENT_CONSUMPTION_NAMESPACE,
    INITIAL_STATE,
    RECENT_EXACT_DAYS,
    SELECTION_CONTRACT_VERSION,
    TIMEZONE_CONTRACT_VERSION,
    USAGE_WINDOW_DAYS,
    DailyActivityPlanConflictError,
    DailyActivityPlanError,
    DailyActivityPlanForbiddenError,
    DailyActivityPlanNotFoundError,
    DailyActivityPlanValidationError,
    PlanScope,
    daypart_windows,
    local_activity_date,
)
from app.domains.routines.infrastructure.sqlalchemy_daily_plan_repository import (
    SqlAlchemyDailyPlanRepository,
)
from app.domains.routines.infrastructure.sqlalchemy_lifecycle import (
    SqlAlchemyLifecycleRepository,
    close_elapsed_dayparts as _close_elapsed_dayparts,
    interrupt_inactive_world_character as _interrupt_inactive_world_character,
)
from app.domains.routines.infrastructure.system_clock import FrozenClock, SystemClock
from app.domains.routines.ports.clock import Clock


def _clock(*, now: datetime | None, clock: Clock | None) -> Clock:
    if now is not None and clock is not None:
        raise ValueError("now_and_clock_are_mutually_exclusive")
    if now is not None:
        return FrozenClock(now)
    return clock or SystemClock()


def prepare_activity_plan(
    db: Any,
    *,
    character_id: str,
    world_id: str,
    user: Any,
    data: Any,
    now: datetime | None = None,
    clock: Clock | None = None,
) -> Any:
    return PrepareDailyPlan(
        SqlAlchemyDailyPlanRepository(db), _clock(now=now, clock=clock)
    )(character_id=character_id, world_id=world_id, user=user, data=data)


def get_activity_plan(
    db: Any,
    *,
    character_id: str,
    world_id: str,
    user: Any,
    now: datetime | None = None,
    clock: Clock | None = None,
) -> Any:
    return GetDailyPlan(
        SqlAlchemyDailyPlanRepository(db), _clock(now=now, clock=clock)
    )(character_id=character_id, world_id=world_id, user=user)


def update_activity_runtime_mode(
    db: Any,
    *,
    character_id: str,
    world_id: str,
    user: Any,
    data: Any,
    now: datetime | None = None,
    clock: Clock | None = None,
) -> Any:
    return UpdateRuntimeMode(
        SqlAlchemyDailyPlanRepository(db), _clock(now=now, clock=clock)
    )(character_id=character_id, world_id=world_id, user=user, data=data)


def reconcile_all_elapsed_routines(
    db: Any,
    *,
    now: datetime | None = None,
    clock: Clock | None = None,
) -> DaypartTransitionCounts:
    return ReconcileElapsedRoutines(
        SqlAlchemyLifecycleRepository(db), _clock(now=now, clock=clock)
    )()


def recover_expired_claims(
    db: Any,
    *,
    now: datetime | None = None,
    clock: Clock | None = None,
) -> RecoveryCounts:
    return RecoverExpiredRoutineClaims(
        SqlAlchemyLifecycleRepository(db), _clock(now=now, clock=clock)
    )()


def close_elapsed_dayparts(
    db: Any,
    *,
    world_character_id: str,
    now: datetime | None = None,
    clock: Clock | None = None,
) -> DaypartTransitionCounts:
    return _close_elapsed_dayparts(
        db,
        world_character_id=world_character_id,
        now=_clock(now=now, clock=clock).now_utc(),
    )


def interrupt_inactive_world_character(
    db: Any,
    *,
    world_character_id: str,
    now: datetime | None = None,
    clock: Clock | None = None,
) -> WorldInterruptionCounts:
    return _interrupt_inactive_world_character(
        db,
        world_character_id=world_character_id,
        now=_clock(now=now, clock=clock).now_utc(),
    )


__all__ = [
    "ActivityRuntimeConflictError",
    "ActivityRuntimeError",
    "ActivityRuntimeNotFoundError",
    "ActivityRuntimeValidationError",
    "Clock",
    "DAYPARTS",
    "DAYPART_START_HOURS",
    "DaypartTransitionCounts",
    "DailyActivityPlanConflictError",
    "DailyActivityPlanError",
    "DailyActivityPlanForbiddenError",
    "DailyActivityPlanNotFoundError",
    "DailyActivityPlanValidationError",
    "DueTick",
    "EVENT_CONSUMPTION_NAMESPACE",
    "FrozenClock",
    "INITIAL_STATE",
    "PlanScope",
    "RECENT_EXACT_DAYS",
    "RecoveryCounts",
    "SELECTION_CONTRACT_VERSION",
    "SystemClock",
    "TIMEZONE_CONTRACT_VERSION",
    "USAGE_WINDOW_DAYS",
    "WorldInterruptionCounts",
    "close_elapsed_dayparts",
    "daypart_windows",
    "get_activity_plan",
    "interrupt_inactive_world_character",
    "latest_due_tick",
    "local_activity_date",
    "prepare_activity_plan",
    "reconcile_all_elapsed_routines",
    "recover_expired_claims",
    "update_activity_runtime_mode",
]
