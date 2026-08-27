"""Stable public surface for social discovery and canonical source writes."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.domains.social.application import (
    KeywordPostLookup,
    SocialSearchBinding,
    current_social_search,
    find_keyword_post_ids,
    register_social_search,
    unregister_social_search,
)
from app.domains.social.application import (
    apply_validated_autonomous_result as _apply_validated_autonomous_result,
)
from app.domains.social.application import (
    create_owner_post as _create_owner_post,
)
from app.domains.social.application import (
    create_owner_reply as _create_owner_reply,
)
from app.domains.social.domain import (
    OwnerPostCommand,
    OwnerReplyCommand,
    SocialSearchState,
    SocialSearchUnavailable,
    SocialWriteConflictError,
    SocialWriteError,
    SocialWriteForbiddenError,
    SocialWriteNotFoundError,
    SocialWriteResult,
    SocialWriteRetryableError,
    ValidatedAutonomousWriteCommand,
)
from app.domains.social.infrastructure.sqlalchemy_write_unit_of_work import (
    SqlAlchemySocialWriteUnitOfWork,
)
from app.domains.social.ports import SocialSearchIndexPort, SocialWriteUnitOfWorkPort


class _PostPayload(Protocol):
    title: str
    body: str


class _ReplyPayload(Protocol):
    body: str


def create_owner_post(
    db: Session,
    *,
    world_id: str,
    current_user: object,
    idempotency_key: str,
    data: _PostPayload,
) -> SocialWriteResult:
    current_user_id = str(current_user.id)
    return _create_owner_post(
        SqlAlchemySocialWriteUnitOfWork(db),
        OwnerPostCommand(
            world_id=world_id,
            current_user_id=current_user_id,
            idempotency_key=idempotency_key,
            title=data.title,
            body=data.body,
        ),
    )


def create_owner_reply(
    db: Session,
    *,
    world_id: str,
    target_post_id: str,
    current_user: object,
    idempotency_key: str,
    data: _ReplyPayload,
) -> SocialWriteResult:
    current_user_id = str(current_user.id)
    return _create_owner_reply(
        SqlAlchemySocialWriteUnitOfWork(db),
        OwnerReplyCommand(
            world_id=world_id,
            current_user_id=current_user_id,
            idempotency_key=idempotency_key,
            target_post_id=target_post_id,
            body=data.body,
        ),
    )


def apply_validated_autonomous_social_result(
    db: Session,
    command: ValidatedAutonomousWriteCommand,
) -> SocialWriteResult:
    return _apply_validated_autonomous_result(
        SqlAlchemySocialWriteUnitOfWork(db), command
    )


__all__ = [
    "KeywordPostLookup",
    "SocialSearchBinding",
    "SocialSearchIndexPort",
    "SocialSearchState",
    "SocialSearchUnavailable",
    "SocialWriteConflictError",
    "SocialWriteError",
    "SocialWriteForbiddenError",
    "SocialWriteNotFoundError",
    "SocialWriteResult",
    "SocialWriteRetryableError",
    "SocialWriteUnitOfWorkPort",
    "SqlAlchemySocialWriteUnitOfWork",
    "ValidatedAutonomousWriteCommand",
    "apply_validated_autonomous_social_result",
    "create_owner_post",
    "create_owner_reply",
    "current_social_search",
    "find_keyword_post_ids",
    "register_social_search",
    "unregister_social_search",
]
