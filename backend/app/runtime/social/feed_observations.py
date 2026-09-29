"""Settle one delivered Feed batch inside one caller-owned short writer unit."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.social.contracts.observations import SocialObservationError
from app.domains.social.models.topics import RecommendationDelivery
from app.runtime.social import observations


def settle_delivery(db: Session, *, world_id: str, actor_id: str,
                    delivery_id: str | None = None, cycle_key: str | None = None,
                    verify_replay: bool = False, observer: Callable | None = None):
    """Read after acquiring the writer; retry persistence, never provider work.

    The Feed lane must finish its preceding transaction before calling this
    function. A savepoint is allowed only for domain ineligibility. Storage and
    integrity failures roll back all receipts and the delivery's settled marker.
    """
    def operation():
        query = select(RecommendationDelivery).where(
            RecommendationDelivery.world_id == world_id,
            RecommendationDelivery.world_character_id == actor_id,
            RecommendationDelivery.state == "delivered")
        query = query.where(RecommendationDelivery.id == delivery_id) if delivery_id is not None else query.where(
            RecommendationDelivery.cycle_key == cycle_key)
        row = db.scalar(query.with_for_update().execution_options(populate_existing=True))
        if row is None:
            return None
        settled = row.trace.get("_activity_observation") == "settled"
        if settled and not verify_replay:
            return row.id
        outcomes = {}
        for post_id in row.post_ids:
            try:
                with db.begin_nested():
                    observations.observe_source(db, world_id=world_id,
                        observer_world_character_id=actor_id, source_social_event_id=None,
                        source_post_id=post_id, lane="feed", observed_at=row.updated_at)
                outcomes[post_id] = {"status": "observed"}
            except SocialObservationError as exc:
                outcomes[post_id] = {"status": "not_applied", "reason": exc.reason_code}
        # Replays still validate receipt/outbox integrity, while retaining the
        # original recorded outcome and delivered-at timestamp.
        if not settled:
            db.execute(update(RecommendationDelivery).where(RecommendationDelivery.id == row.id).values(
                trace={**row.trace, "_activity_observation": "settled",
                    "_activity_observation_results": outcomes}, updated_at=row.updated_at
            ).execution_options(synchronize_session="fetch"))
        return row.id

    if db.get_bind().dialect.name == "sqlite":
        return run_sqlite_session_immediate(db, operation, require_clean=True, observer=observer)
    with db.begin():
        return operation()
