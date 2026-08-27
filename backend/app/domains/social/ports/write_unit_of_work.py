"""Port for one caller-owned canonical social write transaction."""

from __future__ import annotations

from typing import Protocol

from app.domains.social.domain.writes import (
    OwnerPostCommand,
    OwnerReplyCommand,
    SocialWriteResult,
    ValidatedAutonomousWriteCommand,
)


class SocialWriteUnitOfWorkPort(Protocol):
    def create_owner_post(self, command: OwnerPostCommand) -> SocialWriteResult: ...

    def create_owner_reply(self, command: OwnerReplyCommand) -> SocialWriteResult: ...

    def apply_validated_autonomous_result(
        self, command: ValidatedAutonomousWriteCommand
    ) -> SocialWriteResult: ...


__all__ = ["SocialWriteUnitOfWorkPort"]
