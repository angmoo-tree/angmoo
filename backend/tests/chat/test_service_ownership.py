from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.domains.chat.exceptions import MessageForbiddenError, MessageNotFoundError
from app.domains.chat.service.messages import MessageService
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.service.threads import ThreadService
from app.domains.identity.service import message_credentials
from app.runtime.chat import scope_queries
from test_p8_l_d_world_chat_identity import (
    _character,
    _create_tables,
    _installation,
    _seed_world,
    _user,
)


@pytest.mark.parametrize(
    "installation",
    [
        None,
        SimpleNamespace(bootstrap_state="unclaimed", owner_user_id="owner"),
        SimpleNamespace(bootstrap_state="claimed", owner_user_id="other-owner"),
    ],
)
def test_owner_denial_precedes_world_query_with_same_session(installation):
    db = object()
    calls = []

    def local_installation(received_db, *, lock_scope=False):
        calls.append((received_db, lock_scope))
        return installation

    def owned_world_id(*args, **kwargs):
        raise AssertionError("world query must follow accepted installation ownership")

    service = ThreadService(
        MessageSettingsService(),
        SimpleNamespace(
            local_installation=local_installation, owned_world_id=owned_world_id
        ),
        lambda *args, **kwargs: False,
    )
    with pytest.raises(MessageForbiddenError, match="local owner"):
        service._require_world_chat_owner_scope(db, "owner", "world", lock_scope=True)
    assert calls == [(db, True)]


def test_world_denial_follows_installation_and_preserves_lock_scope():
    db = object()
    calls = []

    def local_installation(received_db, *, lock_scope=False):
        calls.append(("installation", received_db, lock_scope))
        return SimpleNamespace(bootstrap_state="claimed", owner_user_id="owner")

    def owned_world_id(received_db, owner_id, world_id, *, lock_scope=False):
        calls.append(("world", received_db, owner_id, world_id, lock_scope))
        return None

    service = ThreadService(
        MessageSettingsService(),
        SimpleNamespace(
            local_installation=local_installation, owned_world_id=owned_world_id
        ),
        lambda *args, **kwargs: False,
    )
    with pytest.raises(MessageNotFoundError, match="World Chat"):
        service._require_world_chat_owner_scope(db, "owner", "world", lock_scope=True)
    assert calls == [
        ("installation", db, True),
        ("world", db, "owner", "world", True),
    ]


def test_joined_reads_keep_attached_identity_filters_and_single_queries():
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner, other = _user("owner"), _user("other")
        requester, responder = (
            _character("requester", owner.id),
            _character("responder", other.id),
        )
        installation = _installation(owner.id)
        db.add_all([owner, other, requester, responder, installation])
        db.flush()
        requester_role, responder_role = _seed_world(
            db,
            owner=owner,
            responder_owner=other,
            world_id="world",
            requester_character=requester,
            responding_character=responder,
            suffix="same-session",
        )
        db.commit()
        # Load identities before counting; the query itself must not copy rows or
        # introduce lazy attribute loads to reconstruct a second session object.
        db.refresh(requester_role)
        db.refresh(responder_role)
        db.refresh(requester)
        db.refresh(responder)
        db.refresh(owner)
        db.refresh(other)
        statements = []
        listener = lambda *args: statements.append(args[2])
        event.listen(engine, "before_cursor_execute", listener)
        try:
            candidates = scope_queries.owner_controlled_world_characters(
                db, owner.id, "world"
            )
            assert candidates == [requester_role]
            assert candidates[0] is requester_role
            assert len(statements) == 1
            statements.clear()
            row = scope_queries.responding_world_character(
                db, "world", responder_role.id
            )
            assert row[0] is responder_role
            assert row[1] is responder
            assert len(statements) == 1
            statements.clear()
            role = scope_queries.world_chat_role(
                db, requester_role.id, world_id="world", expected_owner_id=owner.id
            )
            assert role[0] is requester_role and role[1] is requester
            assert len(statements) == 1
            assert (
                scope_queries.world_chat_role(
                    db, requester_role.id, world_id="world", expected_owner_id=other.id
                )
                is None
            )
            assert (
                scope_queries.responding_world_character(
                    db, "other-world", responder_role.id
                )
                is None
            )
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        responder.moderation_status = "blocked"
        db.flush()
        assert (
            scope_queries.responding_world_character(db, "world", responder_role.id)
            is None
        )
        db.rollback()
        assert (
            scope_queries.responding_world_character(db, "world", responder_role.id)[1]
            is responder
        )


def test_message_credentials_keep_envelope_scope_flush_only_and_caller_rollback(
    monkeypatch,
):
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    scopes, commits = [], []
    monkeypatch.setattr(
        message_credentials.security,
        "encrypt_secret",
        lambda value, *, scope: scopes.append(scope) or "synthetic-envelope",
    )
    monkeypatch.setattr(
        message_credentials.security,
        "fingerprint_secret",
        lambda value: "synthetic-fingerprint",
    )
    with Session(engine) as db:
        owner = _user("owner")
        db.add(owner)
        db.commit()
        event.listen(db, "after_commit", lambda session: commits.append(session))
        credential = message_credentials.upsert_message_credential(
            db, owner.id, "fixture-input", "gemini-2.5-flash-lite"
        )
        assert message_credentials.get_message_credential(db, owner.id) is credential
        assert credential.purpose == "message"
        assert credential.character_id is None
        assert credential.auth_profile_id == "google:message:owner"
        assert credential.label == "쪽지용 Google API key"
        assert (
            scopes[0].owner_id,
            scopes[0].character_id,
            scopes[0].provider,
            scopes[0].purpose,
        ) == ("owner", "", "google", "message")
        assert commits == []
        db.rollback()
        assert message_credentials.get_message_credential(db, owner.id) is None
        credential = message_credentials.upsert_message_credential(
            db, owner.id, "fixture-input", "gemini-2.5-flash-lite"
        )
        db.commit()
        commits.clear()
        changed = message_credentials.upsert_message_credential(
            db, owner.id, "second-fixture", "gemini-2.5-flash"
        )
        assert changed is credential
        message_credentials.clear_message_credential(credential)
        assert credential.enabled is False
        assert credential.encrypted_api_key is None
        assert credential.key_fingerprint is None
        assert commits == []
        db.rollback()
        assert credential.enabled is True
        assert credential.model == "gemini-2.5-flash-lite"


def test_routes_call_actual_owner_services_without_runtime_port_chain():
    from app.api.v1.routes import messages, world_chat, world_chat_response
    from app.runtime.chat import message_composition, world_generation

    assert messages.thread_service is message_composition.thread_service
    assert messages.settings_service is message_composition.settings_service
    assert messages.message_service is message_composition.message_service
    assert world_chat.chat_service is message_composition.thread_service
    assert world_chat_response.chat_service is world_generation
    assert type(messages.thread_service) is ThreadService
    assert type(messages.settings_service) is MessageSettingsService
    assert type(messages.message_service) is MessageService


def test_legacy_send_releases_original_fence_after_unexpected_failure(monkeypatch):
    service = MessageService(object(), MessageSettingsService())
    db, user = object(), object()
    events = []

    def acquire(received_db, received_user, thread_id):
        events.append(("acquire", received_db, received_user, thread_id))
        return "same-fence"

    async def fail(received_db, received_user, thread_id, content):
        events.append(("send", received_db, received_user, thread_id, content))
        raise RuntimeError("unexpected-provider-failure")

    monkeypatch.setattr(service, "_acquire_response_lease", acquire)
    monkeypatch.setattr(service, "_send_message_locked", fail)
    monkeypatch.setattr(
        service,
        "_release_response_lease",
        lambda *args: events.append(("release", *args)),
    )
    with pytest.raises(RuntimeError, match="unexpected-provider-failure"):
        asyncio.run(
            service.send_message(
                db, user, "thread", SimpleNamespace(content=" trimmed ")
            )
        )
    assert events == [
        ("acquire", db, user, "thread"),
        ("send", db, user, "thread", "trimmed"),
        ("release", db, "thread", "same-fence"),
    ]
