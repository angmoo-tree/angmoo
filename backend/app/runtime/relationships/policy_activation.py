"""Process startup boundary: no activity worker is running during enrollment."""

from datetime import UTC, datetime
from sqlalchemy import select
from app.domains.worlds.models import World
from app.domains.relationships.service.policy_activation import activate_policy


def activate_relationship_policies(session_factory):
    now = datetime.now(UTC)
    with session_factory() as db:
        for world_id in db.scalars(select(World.id).where(World.status != 'archived')):
            activate_policy(db, world_id=world_id, now=now)
        db.commit()
