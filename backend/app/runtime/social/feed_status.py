"""Compose Social readiness with a bounded read of durable Routine results."""
from sqlalchemy import select
from pydantic import ValidationError
from app.domains.routines.models.resident import AgentRun
from app.domains.social.schemas.feed_status import FeedAttemptRead, FeedStatusRead
from app.domains.social.service.world_feed import feed_readiness
from app.runtime.social.world_feed_queries import WorldFeedQueries


def read_feed_status(db, *, world_character_id):
    references = WorldFeedQueries(db)
    readiness = feed_readiness(db, references=references, world_character_id=world_character_id)
    wc = references.world_character(world_character_id)
    attempt = None
    if wc is not None:
        runs = db.scalars(select(AgentRun).where(AgentRun.character_id == wc.character_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).limit(20)).all()
        for run in runs:
            payload = (run.gateway_result or {}).get("feed_result")
            if not isinstance(payload, dict) or payload.get("world_id") != wc.world_id or payload.get("world_character_id") != wc.id:
                continue
            if not isinstance(payload.get("result"), str):
                continue
            try:
                attempt = FeedAttemptRead(run_id=run.id, occurred_at=run.completed_at or run.created_at,
                    **{k: payload[k] for k in ("result", "reason_code", "candidate_count", "delivered_count", "delivery_state") if k in payload})
            except ValidationError:
                continue
            break
    return FeedStatusRead(readiness=readiness, last_attempt=attempt)
