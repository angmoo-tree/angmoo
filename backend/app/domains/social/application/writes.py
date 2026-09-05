"""Application use cases for canonical social source writes."""

from __future__ import annotations

from app.domains.social.contracts.writes import (
    OwnerPostCommand,
    OwnerReplyCommand,
    SocialWriteResult,
    ValidatedAutonomousWriteCommand,
)
from app.domains.social.ports.write_unit_of_work import SocialWriteUnitOfWorkPort


def create_owner_post(
    unit_of_work: SocialWriteUnitOfWorkPort,
    command: OwnerPostCommand,
) -> SocialWriteResult:
    return unit_of_work.create_owner_post(command)


def create_owner_reply(
    unit_of_work: SocialWriteUnitOfWorkPort,
    command: OwnerReplyCommand,
) -> SocialWriteResult:
    return unit_of_work.create_owner_reply(command)


def apply_validated_autonomous_result(
    unit_of_work: SocialWriteUnitOfWorkPort,
    command: ValidatedAutonomousWriteCommand,
) -> SocialWriteResult:
    """Apply already-validated creative output without invoking a provider."""

    return unit_of_work.apply_validated_autonomous_result(command)


__all__ = [
    "apply_validated_autonomous_result",
    "create_owner_post",
    "create_owner_reply",
]
