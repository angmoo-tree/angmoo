"""Canonical ownership predicate; the caller retains transaction ownership."""
from sqlalchemy import select
from app.domains.characters.models import Character


def owns_active_character(db, *, owner_id: str, character_id: str) -> bool:
    return db.scalar(select(Character.id).where(Character.id == character_id,
        Character.owner_id == owner_id, Character.deleted_at.is_(None)).limit(1)) is not None
