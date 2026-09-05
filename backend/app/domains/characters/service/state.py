"""Canonical Character state writes inside the caller commit policy."""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.core import unit_of_work
from app.domains.characters import models, schemas
from app.domains.characters.contracts import CharacterOwner
from app.domains.characters.exceptions import CharacterStateNotFoundError
from app.domains.characters.service import profile

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


def save_character_state(
    db: Session, character_id: str, data: schemas.CharacterStateWrite
) -> schemas.CharacterStateRead:
    character = profile.get_character(db, character_id)
    if character is None or character.deleted_at is not None:
        raise CharacterStateNotFoundError(character_id)

    state = upsert_character_state(db, character, data)
    return schemas.CharacterStateRead.model_validate(state)


def save_character_state_for_user(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    data: schemas.CharacterStateWrite,
) -> schemas.CharacterStateRead:
    character = profile.get_character(db, character_id)
    if character is None or character.deleted_at is not None or character.owner_id != user.id:
        raise CharacterStateNotFoundError(character_id)

    state = upsert_character_state(db, character, data)
    return schemas.CharacterStateRead.model_validate(state)
