"""Read-only activity permission input to resident planning rules."""

from datetime import datetime
from typing import Protocol

from app.domains.routines.contracts.activity_policy import ActivityPolicy


class ActivityPlanningContext(Protocol):
    activity_policy: ActivityPolicy


class ResidentClockContext(Protocol):
    run_started_at: datetime
