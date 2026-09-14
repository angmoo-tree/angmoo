from dataclasses import asdict

from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.repository.embedding import MemoryEmbeddingRepository
from app.domains.memory.schemas.embedding import MemoryEmbeddingRead


def _repository(db, workflows):
    return MemoryEmbeddingRepository(db, workflows.batch_repository(db).memory)


def _validate(db, workflows, scope, credential_id):
    if not credential_id or workflows.validate_embedding_credential is None:
        raise MemoryValidationError("memory_embedding_credential_unavailable")
    workflows.validate_embedding_credential(db, scope.owner_id, credential_id)


def read(*, scope, db, workflows):
    value = _repository(db, workflows).read(scope)
    ready, reason = False, "memory_embedding_disabled"
    if value.enabled:
        try:
            _validate(db, workflows, scope, value.credential_id)
            ready, reason = True, None
        except MemoryValidationError:
            reason = "memory_embedding_credential_unavailable"
    return MemoryEmbeddingRead(**asdict(value),
        scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
        ready=ready, reason_code=reason,
        runtime_status=workflows.embedding_runtime_status() if workflows.embedding_runtime_status else "unknown",
        available_credentials=(workflows.embedding_credential_options(db, scope.owner_id, value.credential_id)
            if workflows.embedding_credential_options is not None else []))


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
