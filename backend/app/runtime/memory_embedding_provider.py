"""Subject-owned embedding bindings with exact admitted revision resolution."""
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service.world_credentials import resolve
from app.domains.memory.exceptions import MemoryValidationError


def embedding_material(session, scope, credential_id=None, *, revision=None):
    try:
        from app.runtime.subject_scope import read_scope_presence
        if any(value is None for value in read_scope_presence(session, scope)):
            raise ValueError("embedding_scope_unavailable")
        material = resolve(session, owner_id=scope.owner_id, world_id=scope.world_id,
            world_character_id=scope.subject_world_character_id, purpose="embedding", revision=revision)
        if material.model != "gemini-embedding-2":
            raise ValueError("embedding_model_mismatch")
        return material
    except Exception as exc:
        from app.core.sqlite_concurrency import is_sqlite_contention
        if is_sqlite_contention(exc):
            raise
        raise MemoryValidationError("memory_embedding_credential_unavailable") from None


def validate_embedding_credential(session, scope, credential_id=None, *, revision=None):
    embedding_material(session, scope, revision=revision)
    from app.domains.identity.service.world_credentials import find
    current = find(session, owner_id=scope.owner_id, world_id=scope.world_id,
        world_character_id=scope.subject_world_character_id, purpose="embedding").revision
    return revision if revision is not None else current


class MemoryQueryEmbedder:
    def __init__(self, session_factory, repository_factory):
        self._factory = session_factory
        self._repository_factory = repository_factory

    async def query(self, request, *, deadline):
        from time import monotonic
        from app.domains.memory.contracts.embedding import embedding_text, EMBEDDING_DIMENSIONS
        from app.providers.registry import get_embedding_adapter
        from app.providers.contracts import EmbeddingRequest
        with self._factory() as session:
            repository = self._repository_factory(session)
            config = repository.read(request.scope)
            scope_setting = repository.memory.get_scope_setting(request.scope)
            if not config.enabled or scope_setting is None or not scope_setting.enabled:
                return None
            if config.profile != request.profile:
                raise MemoryValidationError("memory_embedding_profile_changed")
            revision = validate_embedding_credential(session, request.scope)
            material = embedding_material(session, request.scope, revision=revision)
        # The canonical session is closed before network IO begins.
        remaining = min(30.0, deadline-monotonic())
        if remaining <= 0:
            raise TimeoutError("memory_embedding_deadline")
        response = await get_embedding_adapter(config.provider, config.model).embed_measured(EmbeddingRequest(material.reveal(), config.model,
            embedding_text(request.search_text, query=True), EMBEDDING_DIMENSIONS), timeout_seconds=remaining)
        try:
            with self._factory() as session:
                current = self._repository_factory(session).read(request.scope)
                if current != config:
                    raise MemoryValidationError("memory_embedding_settings_changed")
                current_material = embedding_material(session, request.scope, revision=revision)
                if current_material.fingerprint != material.fingerprint:
                    raise MemoryValidationError("memory_embedding_credential_changed")
        except Exception as exc:
            # A rejected late response still consumed an actual provider request.
            exc.physical_attempts = response.physical_attempts
            exc.duration_ms = response.usage.duration_ms
            exc.input_tokens = response.usage.input_tokens
            raise
        return response
