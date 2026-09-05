"""Canonical social source-write contracts.

These values are storage-neutral.  The Social write service owns validation and persistence within the
caller-provided SQLite unit of work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


class SocialWriteError(Exception):
    reason_code = "social_write_error"

    def __init__(self, reason_code: str | None = None) -> None:
        if reason_code:
            self.reason_code = reason_code
        super().__init__(self.reason_code)


class SocialWriteNotFoundError(SocialWriteError):
    reason_code = "social_write_not_found"


class SocialWriteForbiddenError(SocialWriteError):
    reason_code = "social_write_forbidden"


class SocialWriteConflictError(SocialWriteError):
    reason_code = "social_write_conflict"


class SocialWriteRetryableError(SocialWriteError):
    reason_code = "sqlite_busy_retry_exhausted"


@dataclass(frozen=True)
class OwnerPostCommand:
    world_id: str
    current_user_id: str
    idempotency_key: str
    title: str
    body: str


@dataclass(frozen=True)
class OwnerReplyCommand:
    world_id: str
    current_user_id: str
    idempotency_key: str
    target_post_id: str
    body: str


@dataclass(frozen=True)
class ValidatedAutonomousWriteCommand:
    world_id: str
    actor_world_character_id: str
    idempotency_key: str
    operation: Literal["post", "reply"]
    title: str
    body: str
    target_post_id: str | None = None


@dataclass(frozen=True)
class SocialPostSnapshot:
    id: str
    world_id: str
    author_world_character_id: str
    author_name: str
    title: str
    body: str
    post_type: str
    reply_to_post_id: str | None
    created_at: datetime
    can_owner_reply: bool = False


@dataclass(frozen=True)
class SocialWriteDelivery:
    provider_call_count: Literal[0] = 0
    inbox_candidate_id: str | None = None
    inbox_status: Literal["not_applicable", "pending"] = "not_applicable"
    public_reaction_required: Literal[False] = False


@dataclass(frozen=True)
class SocialWriteResult:
    operation: Literal["post", "reply"]
    replayed: bool
    post: SocialPostSnapshot
    delivery: SocialWriteDelivery
    schema_version: Literal["owner-manual-social-v1"] = "owner-manual-social-v1"


__all__ = [
    "OwnerPostCommand",
    "OwnerReplyCommand",
    "SocialPostSnapshot",
    "SocialWriteConflictError",
    "SocialWriteDelivery",
    "SocialWriteError",
    "SocialWriteForbiddenError",
    "SocialWriteNotFoundError",
    "SocialWriteResult",
    "SocialWriteRetryableError",
    "ValidatedAutonomousWriteCommand",
]
