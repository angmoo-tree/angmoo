"""Runtime composition helper for canonical social observations.

Orchestration lanes enter the canonical application contract through this
runtime-owned adapter; none of them writes relationship rows directly.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.runtime.social.sqlalchemy_unit_of_work import (
    SqlAlchemySocialObservationUnitOfWork,
)
from app.domains.social.public import (
    ObservationLane,
    SocialObservationCommand,
    SocialObservationResult,
    observe_social_source,
)


def observe_source(
    db: Session,
    *,
    world_id: str,
    observer_world_character_id: str,
    source_social_event_id: str | None,
    source_post_id: str | None,
    lane: ObservationLane,
    observed_at: datetime,
) -> SocialObservationResult:
    return observe_social_source(
        SqlAlchemySocialObservationUnitOfWork(db),
        SocialObservationCommand(
            world_id=world_id,
            observer_world_character_id=observer_world_character_id,
            source_social_event_id=source_social_event_id,
            source_post_id=source_post_id,
            lane=lane,
            observed_at=observed_at,
        ),
    )


__all__ = ["observe_source"]
