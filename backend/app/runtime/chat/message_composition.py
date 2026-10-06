"""Connect concrete Chat services to their cross-owner SQL collaborator."""

from fastapi import FastAPI

from app.domains.chat.service.evidence import EvidenceService
from app.domains.chat.service.generation import GenerationService
from app.domains.chat.service.messages import MessageService
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.service.threads import ThreadService
from app.runtime.chat import evidence_reads, generation_workflows, scope_queries
from app.domains.social.repository.blocks import world_character_pair_is_blocked

def world_chat_profile(db, *, owner_id, world_id, actor_id):
    from app.domains.identity.service.world_credentials import find, metadata, validate_profile
    from app.domains.chat.exceptions import MessageCredentialInvalidError
    from app.domains.memory.contracts.scope import MemoryScope
    from app.runtime.subject_scope import read_scope_presence
    if any(value is None for value in read_scope_presence(db, MemoryScope(owner_id, world_id, actor_id))):
        raise MessageCredentialInvalidError("world_chat_profile_required")
    value = metadata(find(db, owner_id=owner_id, world_id=world_id, world_character_id=actor_id, purpose="chat"), purpose="chat")
    validate_profile("chat", value.provider, value.model, value.thinking_level)
    return value.model, value.thinking_level


settings_service = MessageSettingsService(world_profile_reader=world_chat_profile)
thread_service = ThreadService(
    settings_service, scope_queries, world_character_pair_is_blocked
)
message_service = MessageService(thread_service, settings_service)


generation_service = GenerationService(
    thread_service, settings_service, generation_workflows
)

evidence_service = EvidenceService(thread_service, evidence_reads)


def configure_chat_services(app: FastAPI) -> None:
    """Bind these same service instances before serving Chat HTTP requests."""
    app.state.chat_thread_service = thread_service
    app.state.chat_settings_service = settings_service
    app.state.chat_message_service = message_service
    app.state.chat_generation_service = generation_service
    app.state.chat_evidence_service = evidence_service
