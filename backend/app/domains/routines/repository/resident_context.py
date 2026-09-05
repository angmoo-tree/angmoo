"""Same-Session activity history reads used for resident decisions."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models


def latest_relationship_review_at(db: Session, *, character_id: str) -> datetime | None:
    return db.scalar(
        select(models.AgentActivityLog.created_at)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type == "relationship_reviewed",
        )
        .order_by(
            models.AgentActivityLog.created_at.desc(),
            models.AgentActivityLog.id.desc(),
        )
        .limit(1)
    )
