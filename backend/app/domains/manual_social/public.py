"""Stable public surface for owner-controlled manual social activity."""

from app.compatibility.manual_social.inbox import (
    ManualInboxRuntimeError,
    candidates as manual_inbox_candidates,
    claim as claim_manual_inbox,
    consume_claims as consume_manual_inbox_claims,
    is_manual_inbox_source,
    release_claims as release_manual_inbox_claims,
)
from app.compatibility.manual_social.legacy import (
    ManualSocialConflictError,
    ManualSocialError,
    ManualSocialForbiddenError,
    ManualSocialNotFoundError,
    create_owner_post,
    create_owner_reply,
    get_owner_world_post_thread,
    list_owner_world_feed,
)
from app.domains.manual_social.domain.inbox import ManualInboxInteractionCandidate

__all__ = [
    "ManualInboxRuntimeError",
    "ManualInboxInteractionCandidate",
    "ManualSocialConflictError",
    "ManualSocialError",
    "ManualSocialForbiddenError",
    "ManualSocialNotFoundError",
    "claim_manual_inbox",
    "consume_manual_inbox_claims",
    "is_manual_inbox_source",
    "manual_inbox_candidates",
    "release_manual_inbox_claims",
    "create_owner_post",
    "create_owner_reply",
    "get_owner_world_post_thread",
    "list_owner_world_feed",
]
