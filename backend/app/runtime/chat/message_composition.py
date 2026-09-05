"""Connect concrete Chat services to their cross-owner SQL collaborator."""

from app.domains.chat.service.evidence import EvidenceService
from app.domains.chat.service.generation import GenerationService
from app.domains.chat.service.messages import MessageService
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.service.threads import ThreadService
from app.runtime.chat import evidence_reads, scope_queries
from app.runtime.relationships.sqlalchemy_social_event import (
    world_character_pair_is_blocked,
)

settings_service = MessageSettingsService()
thread_service = ThreadService(
    settings_service, scope_queries, world_character_pair_is_blocked
)
message_service = MessageService(thread_service, settings_service)


generation_service = GenerationService(thread_service)

evidence_service = EvidenceService(thread_service, evidence_reads)
