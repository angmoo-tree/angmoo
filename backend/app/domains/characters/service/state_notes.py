"""Character memory-note equivalence and optional observation text values."""

from app.domains.characters import models, schemas


def _normalize_state_memory_note(value: str) -> str:
    return " ".join(value.split()).casefold()


def _is_duplicate_memory_note(
    state: models.CharacterState | None, data: schemas.CharacterStateWrite
) -> bool:
    if state is None:
        return False
    incoming_note = _normalize_state_memory_note(data.memory_note)
    saved_note = _normalize_state_memory_note(state.memory_note)
    return bool(incoming_note and incoming_note == saved_note)


def _state_observation_note(data: schemas.CharacterStateWrite) -> str:
    note = getattr(data, "observation_note", None)
    return note.strip() if isinstance(note, str) else ""
