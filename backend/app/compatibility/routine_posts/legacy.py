"""Narrow bridge from the L3 P4 domain to later-stage legacy persistence.

PR F owns routine continuation and atomic publication. The underlying social
write, joint-activity, and agent-run persistence modules are still owned by PR
G/L4, so they remain behind this explicitly temporary adapter instead of being
imported by the domain itself.
"""

from __future__ import annotations

from app import models
from app.cruds import agent_runs as agent_run_crud
from app.domains.social.schemas.community import PostCreate
from app.services import (
    activity_state_contracts,
    agent_activity_policy,
)
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
    "agent_run_crud",
    "models",
    "neutralize_context_text",
    "social_event_runtime",
]
