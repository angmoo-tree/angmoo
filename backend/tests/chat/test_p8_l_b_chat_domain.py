from __future__ import annotations
import app.runtime.chat.message_composition as _actual_runtime_chat_message_composition
from compatibility_retirement_support import alias_retired, export_matches


import asyncio
import importlib

from app.domains.chat import public as chat
from app.compatibility.chat_service import ChatService
from app.domains.chat import policies
from app.domains.chat import models as sqlalchemy_models


def test_legacy_message_service_is_the_canonical_runtime_module() -> None:
    assert alias_retired('app.services.messages', 'app.runtime.chat.sqlalchemy_service')
    assert export_matches('app.services.messages', 'generate_text', _actual_runtime_chat_message_composition.message_service.generate_text) and export_matches('app.runtime.chat.sqlalchemy_service', 'generate_text', _actual_runtime_chat_message_composition.message_service.generate_text)
    assert export_matches('app.services.messages', '_acquire_response_lease', _actual_runtime_chat_message_composition.message_service._acquire_response_lease) and export_matches('app.runtime.chat.sqlalchemy_service', '_acquire_response_lease', _actual_runtime_chat_message_composition.message_service._acquire_response_lease)


def test_legacy_model_and_schema_exports_are_canonical_objects() -> None:
    legacy_models = importlib.import_module('app.domains.chat.models')
    assert legacy_models.CharacterMessageSetting is sqlalchemy_models.CharacterMessageSetting
    assert legacy_models.UserMessagePreference is sqlalchemy_models.UserMessagePreference
    assert legacy_models.MessageThread is sqlalchemy_models.MessageThread
    assert legacy_models.MessageMessage is sqlalchemy_models.MessageMessage
    assert export_matches('app.schemas.messages', 'MessageThreadRead', chat.MessageThreadRead)
    assert export_matches('app.schemas.messages', 'MessageSendRead', chat.MessageSendRead)
    assert export_matches('app.schemas.messages', 'ProfileRef', chat.ProfileRef)


def test_chat_v1_policy_values_remain_frozen() -> None:
    assert policies.MAX_ACTIVE_THREADS == 5
    assert policies.CONTEXT_MESSAGE_LIMIT == 20
    assert policies.CONTEXT_CHAR_LIMIT == 12_000
    assert policies.USER_MESSAGE_LIMIT == 2_000
    assert policies.MODEL_OUTPUT_TOKENS == 1024
    assert policies.MESSAGE_RESPONSE_LEASE_SECONDS == 150
    assert policies.DEFAULT_MESSAGE_MODEL == "gemini-2.5-flash-lite"


class _RuntimeSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def list_threads(self, db: object, user: object) -> str:
        self.calls.append(("list_threads", db, user))
        return "listed"

    async def send_message(
        self, db: object, user: object, thread_id: str, data: object
    ) -> str:
        self.calls.append(("send_message", db, user, thread_id, data))
        return "sent"


def test_application_service_delegates_through_runtime_port() -> None:
    runtime = _RuntimeSpy()
    service = ChatService(runtime)  # type: ignore[arg-type]
    db = object()
    user = object()
    data = object()

    assert service.list_threads(db, user) == "listed"
    assert asyncio.run(service.send_message(db, user, "thread-1", data)) == "sent"
    assert runtime.calls == [
        ("list_threads", db, user),
        ("send_message", db, user, "thread-1", data),
    ]
