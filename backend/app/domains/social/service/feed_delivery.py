"""Persist provider delivery independently from action validation and outcomes."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from sqlalchemy import select, delete, or_
from app.domains.social.models.topics import RecommendationDelivery


class FeedDelivery:
    def __init__(self, db, *, profile, cycle_key, claims, validate=None,
                 validate_completion=None, retain_until_observed=False, transaction=None):
        self.db, self.claims = db, claims
        self.validate = validate
        self.validate_completion = validate_completion
        self.transaction = transaction or self._commit
        self.row = self.transaction(lambda: self._prepare(profile, cycle_key, retain_until_observed))
        self.attempt = (self.row.trace or {}).get("_delivery_attempt", 0)
        self.recovery_key = None
        self.recovery_validator = None

    def _commit(self, operation):
        result = operation()
        self.db.commit()
        return result

    def _prepare(self, profile, cycle_key, retain_until_observed):
        db, claims = self.db, self.claims
        recent = select(RecommendationDelivery.id).where(
            RecommendationDelivery.world_character_id == profile.world_character.id,
        ).order_by(RecommendationDelivery.updated_at.desc(), RecommendationDelivery.id.desc()).limit(199)
        db.execute(delete(RecommendationDelivery).where(
            RecommendationDelivery.world_character_id == profile.world_character.id,
            # The activity being resumed still owns its receipt, even when it
            # is old. Historical cycles retain the existing bounded policy.
            RecommendationDelivery.cycle_key != cycle_key,
            or_(RecommendationDelivery.trace["_activity_observation"].as_string().is_(None),
                RecommendationDelivery.trace["_activity_observation"].as_string() != "pending",
                RecommendationDelivery.state != "delivered"),
            or_(RecommendationDelivery.state.in_(("delivered", "uncertain")),
                RecommendationDelivery.updated_at < datetime.now(UTC) - timedelta(days=1)),
            or_(RecommendationDelivery.updated_at < datetime.now(UTC) - timedelta(days=30),
                RecommendationDelivery.id.not_in(recent)),
        ))
        row = db.scalar(select(RecommendationDelivery).where(
            RecommendationDelivery.world_character_id == profile.world_character.id,
            RecommendationDelivery.cycle_key == cycle_key,
        ))
        if row is None:
            row = RecommendationDelivery(id=str(uuid4()), world_id=profile.world.id,
                world_character_id=profile.world_character.id, cycle_key=cycle_key,
                state="prepared", post_ids=[c.post_id for c in claims.candidates],
                trace={c.post_id: {"sources": c.sources, "lane": c.allocated_lane} for c in claims.candidates})
            db.add(row)
        if retain_until_observed and "_activity_observation" not in (row.trace or {}):
            row.trace = {**(row.trace or {}), "_activity_observation": "pending"}
        return row

    def allow_selection_recovery(self, validate):
        """Authorize one new pure selection request, never invent a response.

        Admission consumes the runtime's existing recovery budget atomically
        with recover_selection(). Merely constructing this object changes no
        uncertain receipt. A consumed attempt survives process interruption.
        """
        if self.attempt != 0:
            raise ValueError("feed_delivery_recovery_exhausted")
        self.recovery_validator = validate
        self.recovery_key = f"feed_selection_delivery:{self.row.id}"

    def recover_selection(self):
        """Called only inside the runtime's recovery-reservation transaction."""
        self._refresh_attempt()
        if self.recovery_validator is None or self.row.state not in {"uncertain", "dispatched"}:
            raise ValueError("feed_delivery_recovery_state_changed")
        self.recovery_validator()
        previous = {"state": self.row.state, "updated_at": self.row.updated_at.isoformat(),
                    "reason": "selection_response_unconfirmed", "attempt": self.attempt}
        self.row.trace = {**self.row.trace, "_delivery_attempt": 1,
                          "_selection_recovery": previous}
        self.row.state = "prepared"
        # The in-memory attempt is accepted only after the outer commit.

    def accept_recovery(self):
        self.attempt = 1

    def _refresh_attempt(self):
        self.db.refresh(self.row)
        if (self.row.trace or {}).get("_delivery_attempt", 0) != self.attempt:
            raise ValueError("feed_delivery_attempt_changed")

    def dispatched(self):
        return self.transaction(self._dispatch)

    def _dispatch(self):
        self._refresh_attempt()
        if self.validate is not None:
            self.validate()
        if self.row.state != "delivered":
            self.row.state = "dispatched"

    def delivered(self):
        return self.transaction(self._deliver)

    def _deliver(self):
        self._refresh_attempt()
        if self.row.state == "delivered":
            return
        # Completion may guard claim ownership, but must not re-run the legacy
        # source check: deletion after dispatch cannot undo actual delivery.
        if self.validate_completion is not None:
            self.validate_completion()
        self.row.state = "delivered"
        for observation in self.claims.observations:
            self.db.refresh(observation)
            observation.status = "observed"
            observation.observed_at = datetime.now(UTC)

    def uncertain(self):
        return self.transaction(self._uncertain)

    def _uncertain(self):
        self._refresh_attempt()
        if self.row.state == "dispatched":
            self.row.state = "uncertain"
