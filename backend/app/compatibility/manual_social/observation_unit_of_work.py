"""SQLAlchemy adapter for the L4 social-observation contract."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.social.domain.observations import (
    SocialObservationCommand,
    SocialObservationError,
    SocialObservationResult,
)
from app.services import social_event_runtime


class SqlAlchemySocialObservationUnitOfWork:
    def __init__(self, session: Session) -> None:
        self._session = session

    def observe(self, command: SocialObservationCommand) -> SocialObservationResult:
        try:
            applied = social_event_runtime.record_social_event_observation(
                self._session,
                world_id=command.world_id,
                observer_world_character_id=command.observer_world_character_id,
                source_social_event_id=command.source_social_event_id,
                source_post_id=command.source_post_id,
                observed_at=command.observed_at,
            )
        except social_event_runtime.SocialEventRuntimeError as exc:
            raise SocialObservationError(exc.reason_code) from exc
        return SocialObservationResult(
            source_social_event_id=applied.source_event.id,
            receipt_id=applied.relationship_change.id,
            relationship_state_id=applied.relationship_state.id,
            replayed=applied.reused,
            lane=command.lane,
        )


__all__ = ["SqlAlchemySocialObservationUnitOfWork"]
