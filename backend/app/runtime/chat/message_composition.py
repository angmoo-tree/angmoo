"""Connect concrete Chat services to their cross-owner SQL collaborator."""

from fastapi import FastAPI

from app.domains.chat.service.evidence import EvidenceService
from app.domains.chat.service.generation import GenerationService
from app.domains.chat.service.messages import MessageService
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.service.threads import ThreadService
from app.runtime.chat import evidence_reads, generation_workflows, scope_queries
from app.domains.social.repository.blocks import world_character_pair_is_blocked

settings_service = MessageSettingsService()
thread_service = ThreadService(
    settings_service, scope_queries, world_character_pair_is_blocked
)
message_service = MessageService(thread_service, settings_service)


generation_service = GenerationService(
    thread_service, settings_service, generation_workflows,
    memory_policy=generation_workflows.capture_memory_policy,
)

evidence_service = EvidenceService(thread_service, evidence_reads)


def configure_chat_services(app: FastAPI, *, session_factory=None, search_runtime=None,
                            recall_mode="social_hybrid") -> None:
    """Bind these same service instances before serving Chat HTTP requests."""
    app.state.chat_thread_service = thread_service
    app.state.chat_settings_service = settings_service
    app.state.chat_message_service = message_service
    app.state.chat_generation_service = generation_service
    app.state.chat_evidence_service = evidence_service
    from app.database import SessionLocal
    from app.domains.chat.service.search_preparation import SearchPreparationService
    from app.runtime.memory.composition import search_preparation_settings
    app.state.chat_search_preparation_service = SearchPreparationService(
        thread_service, session_factory or SessionLocal, search_preparation_settings,
        search_runtime.request_preparation if search_runtime is not None else None,
        enabled=recall_mode == "social_hybrid")
