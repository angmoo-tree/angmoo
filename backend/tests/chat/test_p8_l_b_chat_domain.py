from __future__ import annotations

import asyncio
import importlib

from app.domains.chat import public as chat
from app.domains.chat import policies
from app.domains.chat import models as sqlalchemy_models
from app.runtime.chat import sqlalchemy_service


def test_legacy_message_service_is_the_canonical_runtime_module() -> None:
    legacy = importlib.import_module("app.services.messages")

    assert legacy is sqlalchemy_service
    assert legacy.generate_text is sqlalchemy_service.generate_text
    assert legacy._acquire_response_lease is sqlalchemy_service._acquire_response_lease


def test_legacy_model_and_schema_exports_are_canonical_objects() -> None:
    legacy_models = importlib.import_module("app.domains.chat.models")
    legacy_schemas = importlib.import_module("app.schemas.messages")

    assert legacy_models.CharacterMessageSetting is sqlalchemy_models.CharacterMessageSetting
    assert legacy_models.UserMessagePreference is sqlalchemy_models.UserMessagePreference
    assert legacy_models.MessageThread is sqlalchemy_models.MessageThread
    assert legacy_models.MessageMessage is sqlalchemy_models.MessageMessage
    assert legacy_schemas.MessageThreadRead is chat.MessageThreadRead
    assert legacy_schemas.MessageSendRead is chat.MessageSendRead
    assert legacy_schemas.ProfileRef is chat.ProfileRef


def test_chat_v1_policy_values_remain_frozen() -> None:
    assert policies.MAX_ACTIVE_THREADS == 5
    assert policies.CONTEXT_MESSAGE_LIMIT == 20
    assert policies.CONTEXT_CHAR_LIMIT == 12_000
    assert policies.USER_MESSAGE_LIMIT == 2_000
    assert policies.MODEL_OUTPUT_TOKENS == 1024
    assert policies.MESSAGE_RESPONSE_LEASE_SECONDS == 150
    assert policies.DEFAULT_MESSAGE_MODEL == "gemini-2.5-flash-lite"




def test_application_service_delegates_through_runtime_port(monkeypatch) -> None:
    """The actual owners keep argument, result and lease-finalization behavior."""
    from types import SimpleNamespace
    import pytest
    from app.domains.chat.repository import threads as thread_repository
    from app.domains.chat.service.messages import MessageService
    from app.domains.chat.service.settings import MessageSettingsService
    from app.domains.chat.service.threads import ThreadService

    db = object()
    user = SimpleNamespace(id="owner")
    data = SimpleNamespace(content=" sent ")
    calls = []
    settings = MessageSettingsService()
    threads = ThreadService(settings, object(), lambda *_args: False)
    messages = MessageService(threads, settings)

    def list_threads(received_db, owner_id):
        calls.append(("list_threads", received_db, owner_id))
        return []

    def acquire(received_db, received_user, thread_id):
        calls.append(("acquire", received_db, received_user, thread_id))
        return "same-fence"

    async def send(received_db, received_user, thread_id, content):
        calls.append(("send_message", received_db, received_user, thread_id, content))
        return "sent"

    def release(received_db, thread_id, fence):
        calls.append(("release", received_db, thread_id, fence))

    monkeypatch.setattr(thread_repository, "list_threads", list_threads)
    monkeypatch.setattr(messages, "_acquire_response_lease", acquire)
    monkeypatch.setattr(messages, "_send_message_locked", send)
    monkeypatch.setattr(messages, "_release_response_lease", release)
    listed = threads.list_threads(db, user)
    assert listed.items == []
    assert listed.max_threads == policies.MAX_ACTIVE_THREADS
    assert asyncio.run(messages.send_message(db, user, "thread-1", data)) == "sent"
    assert calls == [
        ("list_threads", db, user.id),
        ("acquire", db, user, "thread-1"),
        ("send_message", db, user, "thread-1", "sent"),
        ("release", db, "thread-1", "same-fence"),
    ]
    failure = RuntimeError("same-provider-failure")

    async def fail(received_db, received_user, thread_id, content):
        calls.append(("failed_send", received_db, received_user, thread_id, content))
        raise failure

    monkeypatch.setattr(messages, "_send_message_locked", fail)
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(messages.send_message(db, user, "thread-1", data))
    assert caught.value is failure
    assert calls[-3:] == [
        ("acquire", db, user, "thread-1"),
        ("failed_send", db, user, "thread-1", "sent"),
        ("release", db, "thread-1", "same-fence"),
    ]
