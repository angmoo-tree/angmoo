"""Persist provider delivery independently from action validation and outcomes."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from sqlalchemy import select, delete, or_
from app.domains.social.models.topics import RecommendationDelivery


class FeedDelivery:
    def __init__(self, db, *, profile, cycle_key, claims, validate=None):
        self.db, self.claims = db, claims
        self.validate = validate
        recent = select(RecommendationDelivery.id).where(
            RecommendationDelivery.world_character_id == profile.world_character.id,
        ).order_by(RecommendationDelivery.updated_at.desc(), RecommendationDelivery.id.desc()).limit(199)
        db.execute(delete(RecommendationDelivery).where(
            RecommendationDelivery.world_character_id == profile.world_character.id,
            or_(RecommendationDelivery.state.in_(("delivered", "uncertain")),
                RecommendationDelivery.updated_at < datetime.now(UTC) - timedelta(days=1)),
            or_(RecommendationDelivery.updated_at < datetime.now(UTC) - timedelta(days=30),
                RecommendationDelivery.id.not_in(recent)),
        ))
        self.row = db.scalar(select(RecommendationDelivery).where(
            RecommendationDelivery.world_character_id == profile.world_character.id,
            RecommendationDelivery.cycle_key == cycle_key,
        ))
        if self.row is None:
            self.row = RecommendationDelivery(id=str(uuid4()), world_id=profile.world.id,
                world_character_id=profile.world_character.id, cycle_key=cycle_key,
                state="prepared", post_ids=[c.post_id for c in claims.candidates],
                trace={c.post_id: {"sources": c.sources, "lane": c.allocated_lane} for c in claims.candidates})
            db.add(self.row)
        db.commit()

    def dispatched(self):
        if self.validate is not None:
            self.validate()
        if self.row.state != "delivered":
            self.row.state = "dispatched"
            self.db.commit()

    def delivered(self):
        if self.row.state == "delivered":
            return
        self.row.state = "delivered"
        for observation in self.claims.observations:
            observation.status = "observed"
            observation.observed_at = datetime.now(UTC)
        self.db.commit()

    def uncertain(self):
        if self.row.state == "dispatched":
            self.row.state = "uncertain"
            self.db.commit()
