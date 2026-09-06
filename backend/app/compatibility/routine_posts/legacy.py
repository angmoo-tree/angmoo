"""Narrow bridge from the L3 P4 domain to later-stage legacy persistence.

PR F owns routine continuation and atomic publication. The underlying social
write, joint-activity, and agent-run persistence modules are still owned by PR
G/L4, so they remain behind this explicitly temporary adapter instead of being
imported by the domain itself.
"""

from __future__ import annotations

from app.runtime.persistence.model_registration import register_models
register_models()
from app.domains.social.schemas.community import PostCreate
from app.runtime.routines import activity_policy as agent_activity_policy
from app.domains.routines.policies import activity_state as activity_state_contracts
from app.runtime.relationships import (
    sqlalchemy_social_event as social_event_runtime,
)

from app.core.context_text import neutralize_context_text
from app.runtime.resident.context import LangGraphResidentContext




__all__ = [
    "LangGraphResidentContext",
    "PostCreate",
    "activity_state_contracts",
    "agent_activity_policy",
    "neutralize_context_text",
    "social_event_runtime",
]
