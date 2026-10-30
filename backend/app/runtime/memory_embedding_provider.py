"""Subject-owned embedding bindings with exact admitted revision resolution."""
from app.core import work_observation as observation
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
        from app.core.postgresql_concurrency import retryable
        if is_sqlite_contention(exc) or retryable(exc):
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

    async def _read(self, operation, *, deadline):
        from app.core.async_session import session_call
        from app.core.postgresql_deadline import read_deadline
        from app.core.postgresql_reads import retry_read, begin_owned_read
        # The owner is never connected on the event loop. Each read attempt
        # owns a fresh snapshot, which is closed in its worker before returning.
        with self._factory() as owner:
            if owner.get_bind().dialect.name != 'postgresql':
                return operation(owner)
            def attempt():
                with self._factory() as session:
                    with read_deadline(session.connection(), deadline):
                        begin_owned_read(session.connection())
                        return operation(session)
            return await session_call(owner, lambda: retry_read(attempt, deadline=deadline))

    async def query(self, request, *, deadline):
        from time import monotonic
        from app.domains.memory.contracts.embedding import embedding_text, EMBEDDING_DIMENSIONS
        from app.providers.registry import get_embedding_adapter
        from app.providers.contracts import EmbeddingRequest
        def prepare(session):
            repository = self._repository_factory(session)
            config = repository.read(request.scope)
            scope_setting = repository.memory.get_scope_setting(request.scope)
            if not config.enabled or scope_setting is None or not scope_setting.enabled:
                return None
            if config.profile != request.profile:
                raise MemoryValidationError("memory_embedding_profile_changed")
            from app.domains.identity.service.world_credentials import find
            binding = find(session, owner_id=request.scope.owner_id, world_id=request.scope.world_id,
                world_character_id=request.scope.subject_world_character_id, purpose="embedding")
            if binding is None:
                raise MemoryValidationError("memory_embedding_credential_unavailable")
            revision = binding.revision
            material = embedding_material(session, request.scope, revision=revision)
            return config, revision, material
        prepared = await self._read(prepare, deadline=deadline)
        if prepared is None:
            return None
        config, revision, material = prepared
        # The canonical session is closed before network IO begins.
        remaining = min(30.0, deadline-monotonic())
        if remaining <= 0:
            raise TimeoutError("memory_embedding_deadline")
        with observation.span("query_embedding", world_id=request.scope.world_id,
                actor_id=request.scope.subject_world_character_id, purpose="query", profile=config.profile,
                credential_revision=revision, credential_id=material.credential_id):
            response = await get_embedding_adapter(config.provider, config.model).embed_measured(EmbeddingRequest(material.reveal(), config.model,
                embedding_text(request.search_text, query=True), EMBEDDING_DIMENSIONS), timeout_seconds=remaining)
        try:
            def validate(session):
                current = self._repository_factory(session).read(request.scope)
                if current != config:
                    raise MemoryValidationError("memory_embedding_settings_changed")
                current_material = embedding_material(session, request.scope, revision=revision)
                if current_material.fingerprint != material.fingerprint:
                    raise MemoryValidationError("memory_embedding_credential_changed")
            await self._read(validate, deadline=deadline)
        except Exception as exc:
            # A rejected late response still consumed an actual provider request.
            exc.physical_attempts = response.physical_attempts
            exc.duration_ms = response.usage.duration_ms
            exc.input_tokens = response.usage.input_tokens
            raise
        return response
