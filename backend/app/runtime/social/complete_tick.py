"""Compose existing Social actions with the original Routines admission and log queries."""

from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.routines.contracts.activity_policy import ActivityPolicy
from app.domains.routines.repository import feed_history
from app.domains.social.service.complete_tick import AgentToolTickService
from app.runtime.social.agent_tools import (
    RuntimeAgentToolActionWorkflows,
    agent_tool_actions,
)
from app.runtime.social.agent_tool_state import agent_tool_state
from app.runtime.resident import activity_policy as agent_activity_policy


class RuntimeAgentToolTickWorkflows(RuntimeAgentToolActionWorkflows):
    def build_activity_policy(
        self, db: Session, *, character_id: str, ignore_active_hours: bool
    ) -> ActivityPolicy:
        return agent_activity_policy.build_activity_policy(
            db, character_id=character_id, ignore_active_hours=ignore_active_hours
        )

    def find_thread_viewed_log_id(
        self, db: Session, *, character_id: str, root_post_id: str, created_at: datetime
    ) -> int | None:
        return feed_history.find_thread_viewed_log_id(
            db,
            character_id=character_id,
            root_post_id=root_post_id,
            created_at=created_at,
        )


agent_tool_tick = AgentToolTickService(
    RuntimeAgentToolTickWorkflows(), agent_tool_actions, agent_tool_state
)
