"""Exact accessible WorldCharacter lookup used by credential authorization."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.world_characters import models


def get_accessible_world_character_id(db: Session, world_id: str, character_id: str, membership_id: str) -> str | None:
    return db.scalar(
        select(models.WorldCharacter.id).where(
            models.WorldCharacter.world_id == world_id,
            models.WorldCharacter.character_id == character_id,
            models.WorldCharacter.membership_id == membership_id,
            models.WorldCharacter.status.in_(("pending", "inactive", "active")),
        )
    )
