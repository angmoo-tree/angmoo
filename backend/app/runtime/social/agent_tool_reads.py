"""Same-Session Routines facts supplied lazily to Social tool reads."""

from sqlalchemy.orm import Session
from app.domains.routines.models import AgentRun, AgentActivityLog
from app.domains.routines.contracts.activity_policy import ActivityPolicy
from app.domains.routines.repository import feed_history
from app.domains.routines.service import activity_logs
from app.domains.social.service.agent_tool_reads import AgentToolReadService
from app.runtime.social.agent_tool_authorization import RuntimeAgentToolReferences
from app.runtime.social.topic_metadata import RuntimeTopicHistoryReferences
from app.runtime.resident import activity_policy as agent_activity_policy


class RuntimeAgentToolReadWorkflows(RuntimeAgentToolReferences):
    @property
    def topic_history(self) -> RuntimeTopicHistoryReferences:
        return RuntimeTopicHistoryReferences()

    def build_activity_policy(
        self, db: Session, *, character_id: str
    ) -> ActivityPolicy:
        return agent_activity_policy.build_activity_policy(
            db, character_id=character_id
        )

    def inbox_delivery_logs(
        self, db: Session, *, run: AgentRun
    ) -> list[AgentActivityLog]:
        return feed_history.list_inbox_delivery_logs(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            created_at=run.created_at,
        )

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


agent_tool_reads = AgentToolReadService(RuntimeAgentToolReadWorkflows())
