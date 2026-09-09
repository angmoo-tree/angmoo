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


def memory_provider(session_factory, owner_id: str, model: str, thinking_level: str = "high"):
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

    return DirectLlmMemorySelectionProvider(snapshot, validate_credential=validate_credential)
