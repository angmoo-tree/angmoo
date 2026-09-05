"""Connect concrete Chat services to their cross-owner SQL collaborator."""

from fastapi import FastAPI

from app.domains.chat.service.evidence import EvidenceService
from app.domains.chat.service.generation import GenerationService
from app.domains.chat.service.messages import MessageService
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.service.threads import ThreadService
from app.runtime.chat import evidence_reads, generation_workflows, scope_queries
from app.runtime.relationships.sqlalchemy_social_event import (
    world_character_pair_is_blocked,
)

settings_service = MessageSettingsService()
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
