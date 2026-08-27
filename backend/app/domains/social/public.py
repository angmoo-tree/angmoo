"""Stable public surface for social discovery and canonical source writes."""

from __future__ import annotations

from app.domains.social.application import (
    KeywordPostLookup,
    SocialSearchBinding,
    current_social_search,
    find_keyword_post_ids,
    register_social_search,
    unregister_social_search,
    apply_validated_autonomous_result,
    create_owner_post,
    create_owner_reply,
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
from app.domains.social.ports import SocialSearchIndexPort, SocialWriteUnitOfWorkPort

apply_validated_autonomous_social_result = apply_validated_autonomous_result


__all__ = [
    "KeywordPostLookup",
    "OwnerPostCommand",
    "OwnerReplyCommand",
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
    "ValidatedAutonomousWriteCommand",
    "apply_validated_autonomous_social_result",
    "create_owner_post",
    "create_owner_reply",
    "current_social_search",
    "find_keyword_post_ids",
    "register_social_search",
    "unregister_social_search",
]
