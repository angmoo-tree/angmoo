"""Memory owns subject model revisions; Identity owns the independent secret."""
from datetime import UTC, datetime
from sqlalchemy import update

from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.models.activity_configuration import MemorySubjectProfile
from app.providers.generation_profiles import validate_generation_profile


def read(db, *, scope, repository):
    setting = repository.get_scope_setting(scope)
    return db.get(MemorySubjectProfile, setting.id) if setting is not None else None


def save(db, *, scope, repository, model, thinking, expected_revision):
    try:
        validate_generation_profile(model, thinking)
    except ValueError:
        raise MemoryValidationError("memory_selection_model_unsupported") from None
    setting = repository.get_or_create_scope_setting(scope)
    row = db.get(MemorySubjectProfile, setting.id, populate_existing=True)
    if expected_revision != (row.version if row else 0):
        raise MemoryConflictError("memory_subject_profile_revision_conflict")
    if row is None:
        row = MemorySubjectProfile(scope_setting_id=setting.id, model_id=model, thinking_level=thinking,
            version=1, updated_at=datetime.now(UTC))
        db.add(row)
    elif (row.model_id, row.thinking_level) != (model, thinking):
        changed = db.execute(update(MemorySubjectProfile).where(MemorySubjectProfile.scope_setting_id == setting.id,
            MemorySubjectProfile.version == expected_revision).values(model_id=model, thinking_level=thinking,
                version=expected_revision + 1, updated_at=datetime.now(UTC)))
        if changed.rowcount != 1:
            raise MemoryConflictError("memory_subject_profile_revision_conflict")
        db.refresh(row)
    db.flush()
    return row.version
