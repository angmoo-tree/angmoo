"""Cross-domain composition of Memory selection and Local message credentials.

Kept above runtime/chat and runtime/memory: Chat already consumes Memory, so
the Memory package must not depend back on Chat's credential composition.
"""

from dataclasses import replace

from app.domains.identity.models import User
from app.domains.memory.exceptions import MemoryValidationError
from app.integrations.llm.memory_selection import DirectLlmMemorySelectionProvider
from app.providers.registry import get_model_spec
from app.providers.generation_profiles import validate_generation_profile
from app.runtime.chat.message_composition import settings_service


def subject_memory_provider(session_factory, scope, *, model, thinking_level,
                            credential_id=None, credential_revision=None, relationship=False):
    """Resolve only this subject's consolidation key, without a provider call."""
    from app.domains.identity.service.world_credentials import resolve
    from app.runtime.memory.scope_queries import read_consolidation_binding
    with session_factory() as session:
        binding = read_consolidation_binding(session, scope, credential_id, credential_revision)
        if binding is None or (binding.model, binding.thinking_level) != (model, thinking_level):
            raise MemoryValidationError("memory_selection_settings_required")
        if credential_id is not None and (binding.credential_id, binding.revision) != (credential_id, credential_revision):
            raise MemoryValidationError("memory_selection_credential_changed")
        material = resolve(session, owner_id=scope.owner_id, world_id=scope.world_id,
            world_character_id=scope.subject_world_character_id, purpose="consolidation", revision=binding.revision)

    def validate_credential():
        with session_factory() as session:
            current = read_consolidation_binding(session, scope, binding.credential_id, binding.revision)
            if current != binding:
                raise MemoryValidationError("memory_selection_credential_changed")
    if relationship:
        from app.integrations.llm.relationship_review import DirectRelationshipReviewProvider
        return DirectRelationshipReviewProvider(material, validate_credential=validate_credential)
    from app.integrations.llm.episode_selection import DirectLlmEpisodeSelectionProvider
    return DirectLlmEpisodeSelectionProvider(material, validate_credential=validate_credential)


def memory_provider(session_factory, owner_id: str, model: str, thinking_level: str = "high", *, episode=False, relationship=False):
    try:
        validate_generation_profile(model, thinking_level)
    except ValueError:
        raise MemoryValidationError("memory_selection_model_unsupported")
    with session_factory() as session:
        user = session.get(User, owner_id)
        if user is None:
            raise MemoryValidationError("memory_selection_settings_required")
        try:
            _, material = settings_service.resolve_message_credential_material(session, user)
            get_model_spec(material.provider, model)
        except Exception:
            raise MemoryValidationError("memory_selection_settings_required") from None
        snapshot = replace(material, model=model, thinking_level=thinking_level)

    def validate_credential() -> None:
        with session_factory() as current_session:
            current_user = current_session.get(User, owner_id)
            try:
                if current_user is None:
                    raise ValueError("owner_missing")
                _, current = settings_service.resolve_message_credential_material(current_session, current_user)
                if (current.credential_id, current.fingerprint) != (snapshot.credential_id, snapshot.fingerprint):
                    raise ValueError("credential_changed")
            except Exception:
                raise MemoryValidationError("memory_selection_credential_changed") from None

    if relationship:
        from app.integrations.llm.relationship_review import DirectRelationshipReviewProvider
        return DirectRelationshipReviewProvider(snapshot, validate_credential=validate_credential)
    if episode:
        from app.integrations.llm.episode_selection import DirectLlmEpisodeSelectionProvider
        return DirectLlmEpisodeSelectionProvider(snapshot, validate_credential=validate_credential)
    return DirectLlmMemorySelectionProvider(snapshot, validate_credential=validate_credential)
