"""Bind tool writes to actual Social timeline and same-Session Routines operations."""

from sqlalchemy.orm import Session
from app.cruds import agents as agent_crud
from app.domains.routines.models import AgentRun, AgentFeedCue
from app.domains.routines.service import activity_logs
from app.domains.social.service.agent_tool_actions import AgentToolActionService
from app.runtime.social.agent_tool_authorization import RuntimeAgentToolReferences
from app.runtime.social import feed_history
from app.runtime.social.timeline import timeline_service


class RuntimeAgentToolActionWorkflows(RuntimeAgentToolReferences):
    def log_activity(
        self,
        db: Session,
        *,
        user_id: str,
        character_id: str,
        action_type: str,
        target_post_id: str | None,
        reason: str,
        result: str,
    ) -> object:
        return activity_logs.log_activity(
            db,
            user_id=user_id,
            character_id=character_id,
            action_type=action_type,
            target_post_id=target_post_id,
            reason=reason,
            result=result,
        )

    def get_pending_feed_cue(
        self, db: Session, character_id: str
    ) -> AgentFeedCue | None:
        return agent_crud.get_pending_feed_cue(db, character_id)

    def mark_pending_feed_cue_used(
        self, db: Session, *, character_id: str, run_id: str, post_id: str
    ) -> None:
        return agent_crud.mark_pending_feed_cue_used(
            db, character_id=character_id, run_id=run_id, post_id=post_id
        )

    def maybe_log_feed_seed_consumed_for_created_post(
        self, db: Session, *, run: AgentRun, created_post_id: str
    ) -> None:
        return feed_history.maybe_log_feed_seed_consumed_for_created_post(
            db, run=run, created_post_id=created_post_id
        )


agent_tool_actions = AgentToolActionService(
    RuntimeAgentToolActionWorkflows(), timeline_service
)
