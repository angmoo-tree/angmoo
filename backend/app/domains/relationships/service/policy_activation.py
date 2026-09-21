"""One-time prospective relationship policy, independent from the C Feed epoch."""

from datetime import UTC, datetime
from app.domains.relationships.models.personalization import RelationshipPolicy


def activate_policy(db, *, world_id, now=None):
    row = db.get(RelationshipPolicy, world_id)
    if row is None:
        row = RelationshipPolicy(world_id=world_id, mode='interpreted', activated_at=now or datetime.now(UTC), version=1)
        db.add(row)
        db.flush()
    return row
