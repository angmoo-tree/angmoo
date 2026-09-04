"""Cross-domain composition of Memory selection and Local message credentials.

Kept above runtime/chat and runtime/memory: Chat already consumes Memory, so
the Memory package must not depend back on Chat's credential composition.
"""

from dataclasses import replace

from app.domains.identity.public import User
from app.domains.memory.domain.errors import MemoryValidationError
from app.integrations.llm.memory_selection import DirectLlmMemorySelectionProvider
from app.providers.registry import MESSAGE_GOOGLE_MODELS, get_model_spec
from app.runtime.chat.sqlalchemy_service import resolve_message_credential_material


def memory_provider(session_factory, owner_id: str, model: str):
    if model not in MESSAGE_GOOGLE_MODELS:
        raise MemoryValidationError("memory_selection_model_unsupported")
    with session_factory() as session:
        user = session.get(User, owner_id)
        if user is None:
            raise MemoryValidationError("memory_selection_settings_required")
        try:
            _, material = resolve_message_credential_material(session, user)
            get_model_spec(material.provider, model)
        except Exception:
            raise MemoryValidationError("memory_selection_settings_required") from None
        return DirectLlmMemorySelectionProvider(replace(material, model=model))
