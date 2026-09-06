"""Read-only activity permission input to resident planning rules."""

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.domains.routines.contracts.activity_policy import ActivityPolicy


class ActivityPlanningContext(Protocol):
    activity_policy: ActivityPolicy


class ResidentClockContext(Protocol):
    run_started_at: datetime


ClipContextText = Callable[[Any, int], str]


class PlanningCharacter(Protocol):
    id: str


class ResidentPlanningContext(ActivityPlanningContext, ResidentClockContext, Protocol):
    db: Session
    run_id: str
    character: PlanningCharacter
