"""Caller-session character facts for local activity settings."""
from app.domains.characters.models import Character

def read_character(db, character_id):
    return db.get(Character, character_id)
