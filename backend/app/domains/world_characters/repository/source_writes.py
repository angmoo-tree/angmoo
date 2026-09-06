"""Nullable actor lookup for source writes; the caller owns policy and transaction."""
from sqlalchemy.orm import Session
from app.domains.world_characters.models import WorldCharacter


def get_source_actor(db: Session, world_character_id: str) -> WorldCharacter | None:
    return db.get(WorldCharacter, world_character_id)
