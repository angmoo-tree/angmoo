from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.contracts.feed_cues import FeedCueIdentity
from app.domains.routines.repository.feed_cues import get_pending_feed_cue


def create_feed_cue(
    db: Session, *, user: FeedCueIdentity, character: FeedCueIdentity, topic: str
) -> models.AgentFeedCue:
    cue = models.AgentFeedCue(
        user_id=user.id,
        character_id=character.id,
        topic=topic.strip(),
        status="pending",
    )
    db.add(cue)
    db.commit()
    db.refresh(cue)
    return cue


def mark_pending_feed_cue_used(
    db: Session, *, character_id: str, run_id: str | None, post_id: str
) -> models.AgentFeedCue | None:
    cue = get_pending_feed_cue(db, character_id)
    if cue is None:
        return None
    cue.status = "used"
    cue.consumed_run_id = run_id
    cue.consumed_post_id = post_id
    cue.consumed_at = datetime.now(UTC)
    db.commit()
    db.refresh(cue)
    return cue
