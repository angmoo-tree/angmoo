from __future__ import annotations

from typing import Protocol

from app.domains.social.domain.observations import (
    SocialObservationCommand,
    SocialObservationResult,
)


class SocialObservationUnitOfWorkPort(Protocol):
    def observe(self, command: SocialObservationCommand) -> SocialObservationResult: ...


__all__ = ["SocialObservationUnitOfWorkPort"]
