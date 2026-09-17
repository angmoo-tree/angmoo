"""Versioned per-scope embedding choice, independent of generation profiles."""
from datetime import UTC, datetime
from sqlalchemy import select, update

from app.domains.memory.contracts.embedding import (
    EMBEDDING_MODEL, EMBEDDING_PROFILE, EMBEDDING_PROVIDER, MemoryEmbeddingConfiguration,
)
from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.models.embedding import MemoryEmbeddingSetting
from app.domains.memory.models.items import MemoryScopeSettingModel


class MemoryEmbeddingRepository:
    def __init__(self, session, memory_repository):
        self.session, self.memory = session, memory_repository

    def read(self, scope):
        self.memory.validate_scope(scope)
        setting = self.memory.get_scope_setting(scope)
        row = None if setting is None else self.session.get(MemoryEmbeddingSetting, setting.id)
        if row is None:
            return MemoryEmbeddingConfiguration()
        return MemoryEmbeddingConfiguration(row.enabled, row.provider, row.model,
                                            row.credential_id, row.profile, row.version)

    def save(self, scope, *, expected_version, enabled, provider, model, credential_id):
        if (provider, model) != (EMBEDDING_PROVIDER, EMBEDDING_MODEL):
            raise MemoryValidationError("memory_embedding_model_unsupported")
        if enabled and not credential_id:
            raise MemoryValidationError("memory_embedding_credential_required")
        setting = self.memory.get_or_create_scope_setting(scope)
        self.session.execute(update(MemoryScopeSettingModel).where(
            MemoryScopeSettingModel.id == setting.id).values(id=setting.id))
        row = self.session.scalar(select(MemoryEmbeddingSetting).where(
            MemoryEmbeddingSetting.scope_setting_id == setting.id).execution_options(populate_existing=True))
        if (0 if row is None else row.version) != expected_version:
            raise MemoryConflictError("memory_embedding_version_conflict")
        if row is None:
            row = MemoryEmbeddingSetting(scope_setting_id=setting.id, version=0)
            self.session.add(row)
        row.enabled, row.provider, row.model = enabled, provider, model
        row.credential_id, row.profile = credential_id, EMBEDDING_PROFILE
        row.version += 1
        row.updated_at = datetime.now(UTC)
        self.session.flush()
        return self.read(scope)

