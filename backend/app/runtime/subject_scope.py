"""Read current owner, World and actor presence in the caller session."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Base
from app.domains.memory.contracts.scope import MemoryScope

def read_scope_presence(session: Session, scope: MemoryScope) -> tuple[str | None, str | None, str | None]:
    users = Base.metadata.tables["users"]
    worlds = Base.metadata.tables["worlds"]
    world_characters = Base.metadata.tables["world_characters"]
    owner_exists = session.scalar(
        select(users.c.id).where(
            users.c.id == scope.owner_id,
            users.c.deleted_at.is_(None),
        )
    )
    world_exists = session.scalar(
        select(worlds.c.id).where(
            worlds.c.id == scope.world_id,
            worlds.c.owner_user_id == scope.owner_id,
            worlds.c.archived_at.is_(None),
        )
    )
    subject_exists = session.scalar(
        select(world_characters.c.id).where(
            world_characters.c.id == scope.subject_world_character_id,
            world_characters.c.world_id == scope.world_id,
            world_characters.c.status == "active",
        )
    )
    return owner_exists, world_exists, subject_exists
