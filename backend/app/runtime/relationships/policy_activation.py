"""Process startup boundary: no activity worker is running during enrollment."""

from datetime import UTC, datetime
from sqlalchemy import select
from app.domains.worlds.models import World
from app.domains.relationships.service.policy_activation import activate_policy
from app.domains.relationships.models.personalization import RelationshipPolicy
from app.domains.identity.service.environment import lock_environment_admission


def initialize_default_space_policy(db, world: World) -> bool:
    """Enroll only a missing policy inside the default-space command's UoW.

    Reuse the existing admission lock to serialize missing-policy repair. The
    policy owner rechecks after locking and preserves all existing policy data.
    No topics, provider calls, separate Session or commit are introduced.
    """
    if db.get(RelationshipPolicy, world.id) is not None:
        return False
    lock_environment_admission(db, world.owner_user_id)
    activate_policy(db, world_id=world.id)
    return True


def activate_relationship_policies(session_factory):
    now = datetime.now(UTC)
    with session_factory() as db:
        for world_id in db.scalars(select(World.id).where(World.status != 'archived')):
            activate_policy(db, world_id=world_id, now=now)
        db.commit()
