"""Canonical Character state writes inside the caller commit policy."""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.core import unit_of_work
from app.domains.characters import models, schemas

def upsert_character_state(
    db: Session, character: models.Character, data: schemas.CharacterStateWrite
) -> models.CharacterState:
    state = db.get(models.CharacterState, character.id)
    now = datetime.now(timezone.utc)
    if state is None:
        state = models.CharacterState(
            character_id=character.id,
            mood=data.mood,
            summary=data.summary,
            memory_note=data.memory_note,
            updated_at=now,
        )
        db.add(state)
    else:
        state.mood = data.mood
        state.summary = data.summary
        state.memory_note = data.memory_note
        state.updated_at = now

    unit_of_work.finish_write(db, state)
    return state
