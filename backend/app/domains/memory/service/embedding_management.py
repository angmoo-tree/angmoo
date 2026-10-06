from dataclasses import asdict

from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.repository.embedding import MemoryEmbeddingRepository
from app.domains.memory.schemas.embedding import MemoryEmbeddingRead


def _repository(db, workflows):
    return MemoryEmbeddingRepository(db, workflows.batch_repository(db).memory)


def _validate(db, workflows, scope, credential_id):
    if credential_id is not None or workflows.validate_embedding_credential is None:
        raise MemoryValidationError("memory_embedding_credential_unavailable")
    workflows.validate_embedding_credential(db, scope)


def read(*, scope, db, workflows):
    value = _repository(db, workflows).read(scope)
    ready, reason = False, "memory_embedding_disabled"
    if value.enabled:
        try:
            _validate(db, workflows, scope, None)
            ready, reason = True, None
        except MemoryValidationError:
            reason = "memory_embedding_credential_unavailable"
    from app.domains.memory.repository.index_preparation import status
    setting = workflows.batch_repository(db).memory.get_scope_setting(scope)
    preparation = status(db, None if setting is None else setting.id)
    return MemoryEmbeddingRead(**{**asdict(value), "credential_id": None},
        scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
        ready=ready, reason_code=reason,
        runtime_status=workflows.embedding_runtime_status() if workflows.embedding_runtime_status else "unknown",
        available_credentials=[], preparation_state=preparation["state"], preparation_revision=preparation["revision"])


def start_preparation(*, scope, db, workflows, data):
    from datetime import UTC, datetime
    from app.domains.memory.repository.index_preparation import start
    try:
        material = workflows.validate_embedding_credential(db, scope)
        result = start(db, workflows.batch_repository(db).memory, scope,
            expected_revision=data.expected_revision, credential_revision=material,
            now=datetime.now(UTC))
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def save(*, scope, db, workflows, data):
    try:
        repo = _repository(db, workflows)
        repo.memory.validate_scope(scope)
        # Validate selected credential even when OFF, so foreign IDs cannot be persisted.
        if data.credential_id is not None or data.enabled:
            _validate(db, workflows, scope, data.credential_id)
        repo.save(scope, **data.model_dump())
        db.commit()
    except Exception:
        db.rollback()
        raise
    return read(scope=scope, db=db, workflows=workflows)
