"""Stable actor lock for short preparation writes (no network work)."""
from sqlalchemy import select
from app.domains.world_characters.models import WorldCharacter


def lock_preparation_actor(db, world_character_id):
    return db.scalar(select(WorldCharacter).where(
        WorldCharacter.id == world_character_id).with_for_update())
