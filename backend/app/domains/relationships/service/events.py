"""Canonical event eligibility and source invalidation in the caller transaction."""
from datetime import datetime
from typing import Literal
from sqlalchemy.orm import Session
from app.domains.relationships.repository import events as event_repository
from app.domains.relationships.policies.events import _aware_utc
from app.domains.relationships.service.projection_events import _enqueue_source_exclusion_outbox


def exclude_events_for_posts(
    db: Session,
    *,
    post_ids: list[str],
    reason: Literal["source_deleted", "source_hidden"],
    invalidated_at: datetime,
) -> int:
    unique_post_ids = sorted({post_id for post_id in post_ids if post_id})
    if not unique_post_ids:
        return 0
    event_ids = event_repository.source_event_ids(db, unique_post_ids=unique_post_ids)
    changed = 0
    for event_id in event_ids:
        event = event_repository.find_event_for_update(db, event_id=event_id)
        if event is None:
            continue
        if (
            event.retrieval_status != "excluded"
            or event.invalidation_reason != reason
        ):
            event.retrieval_status = "excluded"
            event.invalidated_at = _aware_utc(invalidated_at)
            event.invalidation_reason = reason
            changed += 1
        _enqueue_source_exclusion_outbox(db, event=event, reason=reason)
    db.flush()
    return changed
