"""Execution contract for one caller-owned canonical social write transaction."""

from __future__ import annotations

from typing import Protocol

from app.domains.social.contracts.writes import (
    OwnerPostCommand,
    OwnerReplyCommand,
    OwnerLikeCommand,
    SocialWriteResult,
    ValidatedAutonomousWriteCommand,
)
from app.domains.social.schemas.manual import ManualSocialLikeRead


class SocialWriteUnitOfWorkPort(Protocol):
    def create_owner_post(self, command: OwnerPostCommand) -> SocialWriteResult: ...

    def create_owner_reply(self, command: OwnerReplyCommand) -> SocialWriteResult: ...
    def set_owner_like(self, command: OwnerLikeCommand) -> ManualSocialLikeRead: ...

    def apply_validated_autonomous_result(
        self, command: ValidatedAutonomousWriteCommand
    ) -> SocialWriteResult: ...


__all__ = ["SocialWriteUnitOfWorkPort"]
