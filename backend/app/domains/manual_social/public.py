"""Stable public surface for owner-controlled manual social activity."""

from app.compatibility.manual_social.inbox import (
    ManualInboxRuntimeError,
    is_manual_inbox_source,
)
from app.compatibility.manual_social.inbox import (
    candidates as manual_inbox_candidates,
)
from app.compatibility.manual_social.inbox import (
    claim as claim_manual_inbox,
)
from app.compatibility.manual_social.inbox import (
    consume_claims as consume_manual_inbox_claims,
)
from app.compatibility.manual_social.inbox import (
    release_claims as release_manual_inbox_claims,
)
from app.compatibility.manual_social.legacy import (
    get_owner_world_post_thread,
    list_owner_world_feed,
)
from app.domains.manual_social.domain.inbox import ManualInboxInteractionCandidate

__all__ = [
    "ManualInboxInteractionCandidate",
    "ManualInboxRuntimeError",
    "claim_manual_inbox",
    "consume_manual_inbox_claims",
    "get_owner_world_post_thread",
    "is_manual_inbox_source",
    "list_owner_world_feed",
    "manual_inbox_candidates",
    "release_manual_inbox_claims",
]
