"""Application use case for one canonical source observation."""

from __future__ import annotations

from app.domains.social.domain.observations import (
    SocialObservationCommand,
    SocialObservationResult,
)
from app.domains.social.ports.observation_unit_of_work import (
    SocialObservationUnitOfWorkPort,
)


def observe_social_source(
    unit_of_work: SocialObservationUnitOfWorkPort,
    command: SocialObservationCommand,
) -> SocialObservationResult:
    return unit_of_work.observe(command)


__all__ = ["observe_social_source"]
