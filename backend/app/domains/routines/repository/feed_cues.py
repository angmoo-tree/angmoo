from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models


def get_pending_feed_cue(db: Session, character_id: str) -> models.AgentFeedCue | None:
    return db.scalar(
        select(models.AgentFeedCue)
        .where(
            models.AgentFeedCue.character_id == character_id,
            models.AgentFeedCue.status == "pending",
        )
        .order_by(models.AgentFeedCue.created_at.asc(), models.AgentFeedCue.id.asc())
        .limit(1)
    )
