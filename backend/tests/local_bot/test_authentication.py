from types import SimpleNamespace

import pytest

from app.domains.local_bot.contracts.authentication import (
    LocalBotAuthenticationWorkflows,
)
from app.domains.local_bot.exceptions import LocalBotForbiddenError, LocalBotModeError
from app.domains.local_bot.service import authentication


def test_authentication_preserves_attached_values_and_owner_lookup_order(monkeypatch):
    db = object()
    events = []
    key = SimpleNamespace(character_id="bot", owner_id="owner")
    character = SimpleNamespace(id="bot", deleted_at=None, execution_mode="local")
    owner = SimpleNamespace(id="owner", deleted_at=None, email="owner@example.test")

    def lookup_key(session, token_hash):
        assert session is db
        assert token_hash == authentication.security.hash_token("angmoo_local_fixture")
        events.append("key")
        return key

    def lookup_character(session, character_id):
        assert session is db and character_id == "bot"
        events.append("character")
        return character

    def lookup_user(session, user_id):
        assert session is db and user_id == "owner"
        events.append("user")
        return owner

    def mark_used(session, row):
        assert session is db and row is key
        events.append("persist-used")
        return row

    monkeypatch.setattr(
        authentication.key_repository, "get_active_local_key_by_hash", lookup_key
    )
    monkeypatch.setattr(authentication.key_records, "mark_local_key_used", mark_used)
    monkeypatch.setattr(
        authentication.demo_lock, "is_locked_demo_user", lambda value: False
    )
    result = authentication.authenticate_local_bot(
        db,
        "  angmoo_local_fixture  ",
        workflows=LocalBotAuthenticationWorkflows(lookup_character, lookup_user),
    )
    assert (
        result.character is character
        and result.user is owner
        and result.local_key is key
    )
    assert events == ["key", "character", "user", "persist-used"]


def test_authentication_rejections_stop_reads_before_persisting_key_usage(monkeypatch):
    db = object()
    key = SimpleNamespace(character_id="bot", owner_id="owner")
    events = []
    monkeypatch.setattr(
        authentication.key_repository,
        "get_active_local_key_by_hash",
        lambda session, token_hash: key,
    )

    def unexpected_write(*args, **kwargs):
        raise AssertionError("Rejected authentication must not persist last-used")

    monkeypatch.setattr(
        authentication.key_records, "mark_local_key_used", unexpected_write
    )
    cases = [
        (None, None, LocalBotForbiddenError, ["character"]),
        (
            SimpleNamespace(deleted_at="deleted", execution_mode="local"),
            None,
            LocalBotForbiddenError,
            ["character"],
        ),
        (
            SimpleNamespace(deleted_at=None, execution_mode="llm"),
            None,
            LocalBotModeError,
            ["character"],
        ),
        (
            SimpleNamespace(deleted_at=None, execution_mode="local"),
            None,
            LocalBotForbiddenError,
            ["character", "user"],
        ),
        (
            SimpleNamespace(deleted_at=None, execution_mode="local"),
            SimpleNamespace(deleted_at="deleted"),
            LocalBotForbiddenError,
            ["character", "user"],
        ),
    ]
    for character, owner, error, expected in cases:
        events.clear()

        def get_character(session, character_id):
            assert session is db
            events.append("character")
            return character

        def get_user(session, user_id):
            assert session is db
            events.append("user")
            return owner

        with pytest.raises(error):
            authentication.authenticate_local_bot(
                db,
                "angmoo_local_fixture",
                workflows=LocalBotAuthenticationWorkflows(get_character, get_user),
            )
        assert events == expected
