"""Owner-authorized selected key reuse without copying the underlying secret."""
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.repository.credentials import get_credential
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.memory.exceptions import MemoryValidationError


def embedding_material(session, owner_id, credential_id):
    try:
        row = get_credential(session, credential_id)
        # No character filter: explicit selection authorizes reuse within this owner.
        material = CredentialResolver.resolve_llm_credential(row,
            purpose=CredentialPurpose.MEMORY_EMBEDDING, owner_id=owner_id)
        if material.provider != "google":
            raise ValueError("provider_mismatch")
        return material
    except Exception:
        raise MemoryValidationError("memory_embedding_credential_unavailable") from None


def validate_embedding_credential(session, owner_id, credential_id):
    embedding_material(session, owner_id, credential_id)


class MemoryQueryEmbedder:
    def __init__(self, session_factory, repository_factory):
        self._factory = session_factory
        self._repository_factory = repository_factory

    async def query(self, request, *, deadline):
        from time import monotonic
        from app.domains.memory.contracts.embedding import embedding_text, EMBEDDING_DIMENSIONS
        from app.providers.gemini import GeminiAdapter
        from app.providers.contracts import EmbeddingRequest
        with self._factory() as session:
            repository = self._repository_factory(session)
            config = repository.read(request.scope)
            scope_setting = repository.memory.get_scope_setting(request.scope)
            if not config.enabled or scope_setting is None or not scope_setting.enabled:
                return None
            if config.profile != request.profile:
                raise MemoryValidationError("memory_embedding_profile_changed")
            material = embedding_material(session, request.scope.owner_id, config.credential_id)
        # The canonical session is closed before network IO begins.
        remaining = min(30.0, deadline-monotonic())
        if remaining <= 0:
            raise TimeoutError("memory_embedding_deadline")
        response = await GeminiAdapter().embed_measured(EmbeddingRequest(material.reveal(), config.model,
            embedding_text(request.search_text, query=True), EMBEDDING_DIMENSIONS), timeout_seconds=remaining)
        try:
            with self._factory() as session:
                current = self._repository_factory(session).read(request.scope)
                if current != config:
                    raise MemoryValidationError("memory_embedding_settings_changed")
                current_material = embedding_material(session, request.scope.owner_id, config.credential_id)
                if current_material.fingerprint != material.fingerprint:
                    raise MemoryValidationError("memory_embedding_credential_changed")
        except Exception as exc:
            # A rejected late response still consumed an actual provider request.
            exc.physical_attempts = response.physical_attempts
            exc.duration_ms = response.usage.duration_ms
            exc.input_tokens = response.usage.input_tokens
            raise
        return response
