"""HTTP dependencies for actual application-composed Chat services."""

from typing import cast

from fastapi import Request

from app.api.identity_dependencies import browser_session, get_current_user
from app.database import get_db
from app.domains.chat.service.evidence import EvidenceService
from app.domains.chat.service.generation import GenerationService
from app.domains.chat.service.messages import MessageService
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.service.threads import ThreadService


def get_thread_service(request: Request) -> ThreadService:
    service = getattr(request.app.state, "chat_thread_service", None)
    if service is None:
        raise RuntimeError("Chat thread_service is not configured")
    return cast(ThreadService, service)


def get_settings_service(request: Request) -> MessageSettingsService:
    service = getattr(request.app.state, "chat_settings_service", None)
    if service is None:
        raise RuntimeError("Chat settings_service is not configured")
    return cast(MessageSettingsService, service)


def get_message_service(request: Request) -> MessageService:
    service = getattr(request.app.state, "chat_message_service", None)
    if service is None:
        raise RuntimeError("Chat message_service is not configured")
    return cast(MessageService, service)


def get_generation_service(request: Request) -> GenerationService:
    service = getattr(request.app.state, "chat_generation_service", None)
    if service is None:
        raise RuntimeError("Chat generation_service is not configured")
    return cast(GenerationService, service)


def get_evidence_service(request: Request) -> EvidenceService:
    service = getattr(request.app.state, "chat_evidence_service", None)
    if service is None:
        raise RuntimeError("Chat evidence_service is not configured")
    return cast(EvidenceService, service)
