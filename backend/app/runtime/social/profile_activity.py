"""Bind the existing activity-log query/filter to the public profile projection."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.agent_runs import AgentActivityLog
from app.cruds import agents as agent_crud
from app.domains.social.constants import HIDDEN_AGENT_ACTIVITY_ACTION_TYPES
from app.domains.social.contracts.activity import PublicActivityLog
from app.domains.social.service.profile_activity import ProfileActivityService


class SqlAlchemyProfileActivityReads:
    def recent_activity_logs(self, db: Session, *, character_id: str) -> list[PublicActivityLog]:
        return agent_crud.filter_visible_activity_logs(
                        list(
                            db.scalars(
                                select(AgentActivityLog)
                                .where(AgentActivityLog.character_id == character_id)
                                .where(
                                    AgentActivityLog.action_type.not_in(
                                        HIDDEN_AGENT_ACTIVITY_ACTION_TYPES
                                    )
                                )
                                .order_by(
                                    AgentActivityLog.created_at.desc(),
                                    AgentActivityLog.id.desc(),
                                )
                                .limit(80)
                            )
                        ),
                        limit=20,
                    )


profile_activity_service = ProfileActivityService(SqlAlchemyProfileActivityReads())
