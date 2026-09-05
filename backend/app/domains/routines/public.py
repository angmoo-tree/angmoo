"""Stable public API for deterministic daily planning and lifecycle."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.domains.routines.application.reconcile_lifecycle import (
    ReconcileElapsedRoutines,
    RecoverExpiredRoutineClaims,
)
from app.domains.routines.exceptions import ActivityRuntimeConflictError, ActivityRuntimeError, ActivityRuntimeNotFoundError, ActivityRuntimeValidationError
from app.domains.routines.contracts.lifecycle import DaypartTransitionCounts, DueTick, RecoveryCounts, WorldInterruptionCounts
from app.domains.routines.service.scheduling import latest_due_tick
from app.domains.routines.infrastructure.sqlalchemy_lifecycle import (
    SqlAlchemyLifecycleRepository,
    close_elapsed_dayparts as _close_elapsed_dayparts,
    interrupt_inactive_world_character as _interrupt_inactive_world_character,
)
from app.domains.routines.utils.clock import FrozenClock, SystemClock, resolve_clock as _clock
from app.domains.routines.service.plans import prepare_activity_plan, get_activity_plan, update_activity_runtime_mode
from app.domains.routines.contracts.plans import PlanScope
from app.domains.routines.constants import DAYPARTS, DAYPART_START_HOURS, EVENT_CONSUMPTION_NAMESPACE, INITIAL_STATE, RECENT_EXACT_DAYS, SELECTION_CONTRACT_VERSION, TIMEZONE_CONTRACT_VERSION, USAGE_WINDOW_DAYS
from app.domains.routines.exceptions import DailyActivityPlanConflictError, DailyActivityPlanError, DailyActivityPlanForbiddenError, DailyActivityPlanNotFoundError, DailyActivityPlanValidationError
from app.domains.routines.policies.planning import daypart_windows, local_activity_date
from app.domains.routines.contracts.clock import Clock, ClockPort


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
    "ClockPort",
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
