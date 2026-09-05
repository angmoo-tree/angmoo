"""Shared extraction preserves error identity and the two existing cursor formats."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
import json
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from starlette.responses import JSONResponse

from app import exceptions, pagination
from app.core import request_limits, sqlite_concurrency
from app.domains.device_home import repository as home
from app.domains.device_home.exceptions import InvalidWorldSurfaceCursorError
from app.domains.social.public import (
    SocialWriteRetryableError,
    WorldCharacterSocialProfileQuery,
    WorldCharacterSocialProfileValidationError,
)
from app.runtime import persistence
from app.runtime.social import sqlalchemy_profile_repository as social


# Compatibility vectors from de83dae's cursor functions, using only the public
# synthetic secret below, nonce bytes(range(12)), and these synthetic IDs.
SOCIAL_CURSOR = (
    "AAECAwQFBgcICQoL8C5f5MftBwB-uaN0iC44VmTefYJ9vCnShWUriR9T-uh8jb03bQ0avtVZ"
    "jalQ2f1f55ljuFZT5kEBkANjCP9y_O5_9WGmcJT_sNiLs9_74bp_Ztm1rwnaEwl66EDPeeL6J"
    "HHZkUMKBW458tlkV1OB7D8d4L8jfYRwq9nj-GEf0dRM6UYWdf2-YhtS7ruyXySOFBlh4epGM"
    "8NovaQStnCzNLTMPFW33NdTZhkNAs8I2U-P7-0EItkyo-zMQJCRVA"
)
HOME_CURSOR = "eyJ1cGRhdGVkX2F0IjoiMjAyNi0wOS0wNVQwMTowMjowMyIsIndvcmxkX2lkIjoid29ybGQtZzIifQ"
NOW = datetime(2026, 9, 5, 1, 2, 3)


@pytest.mark.parametrize("name,reason", [
    ("SqliteConcurrencyError", "sqlite_concurrency_error"),
    ("SqliteBusyRetryExhausted", "sqlite_busy_retry_exhausted"),
    ("SqliteTaskQueueFull", "sqlite_task_queue_full"),
])
def test_shared_sqlite_errors_preserve_existing_catch_identity(name, reason):
    error_type = getattr(exceptions, name)
    assert getattr(sqlite_concurrency, name) is error_type
    assert getattr(persistence, name) is error_type
    assert issubclass(error_type, RuntimeError)
    error = error_type("existing detail")
    assert error.reason_code == reason
    assert str(error) == "existing detail"
    assert error.args == ("existing detail",)
    with pytest.raises(sqlite_concurrency.SqliteConcurrencyError):
        raise error


@pytest.mark.parametrize("excess", [0, 1])
def test_request_body_limit_catches_the_shared_error_for_streamed_chunks(excess):
    assert request_limits.RequestBodyTooLargeError is exceptions.RequestBodyTooLargeError
    assert exceptions.RequestBodyTooLargeError.__bases__ == (Exception,)
    limit = request_limits.DEFAULT_REQUEST_BODY_MAX_BYTES
    messages = [
        {"type": "http.request", "body": b"a" * (limit - 1), "more_body": True},
        {"type": "http.request", "body": b"b" * (1 + excess), "more_body": False},
    ]
    sent, completed = [], []
    scope = {"type": "http", "path": "/api/v1/posts", "method": "POST", "headers": []}

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        size = 0
        while True:
            message = await receive()
            size += len(message["body"])
            if not message["more_body"]:
                break
        completed.append(size)
        await JSONResponse({"bytes": size})(scope, receive, send)

    asyncio.run(request_limits.RequestBodyLimitMiddleware(downstream)(scope, receive, send))
    response = json.loads(b"".join(message.get("body", b"") for message in sent))
    assert sent[0]["status"] == (413 if excess else 200)
    assert response == ({"detail": "Request body exceeds the allowed limit."} if excess else {"bytes": limit})
    assert completed == ([] if excess else [limit])


def test_shared_busy_error_keeps_different_social_and_autonomy_http_contracts(monkeypatch):
    from app.api.v1.routes import agents, manual_social

    with pytest.raises(HTTPException) as social_error:
        manual_social._raise_error(SocialWriteRetryableError())
    assert social_error.value.status_code == 503
    assert social_error.value.detail == "sqlite_busy_retry_exhausted"

    detail = "autonomy_activation_retryable: existing message"

    def busy(*args, **kwargs):
        raise agents.agent_service.AgentAutonomyRetryableError(detail)

    monkeypatch.setattr(agents.agent_service, "update_settings", busy)
    with pytest.raises(HTTPException) as autonomy_error:
        agents.update_settings("synthetic-character", None, db=None, user=None)
    assert autonomy_error.value.status_code == 409
    assert autonomy_error.value.detail == detail
    assert agents.agent_service.SqliteBusyRetryExhausted is exceptions.SqliteBusyRetryExhausted


def test_device_home_decodes_existing_cursor_and_emits_identical_bytes():
    assert home._decode_cursor(HOME_CURSOR) == (NOW.isoformat(), "world-g2")
    assert home._encode_cursor(NOW, "world-g2") == HOME_CURSOR
    assert home._decode_cursor(None) == (None, None)


@pytest.mark.parametrize("payload", [
    b"not-json", b'{"updated_at":"invalid","world_id":"world-g2"}',
    b'{"updated_at":"2026-09-05T01:02:03","world_id":""}',
])
def test_device_home_cursor_payload_errors_remain_owned_by_device_home(payload):
    with pytest.raises(InvalidWorldSurfaceCursorError) as error:
        home._decode_cursor(pagination.encode_cursor_bytes(payload))
    assert error.value.reason_code == "invalid_world_surface_cursor"


def social_query():
    return WorldCharacterSocialProfileQuery(
        world_id="world-g2", world_character_id="wc-g2", current_user_id="viewer-g2",
        tab="posts", cursor=SOCIAL_CURSOR,
    )


def test_social_cursor_accepts_prior_authenticated_format_and_remains_opaque(monkeypatch):
    monkeypatch.setattr(social, "settings", SimpleNamespace(app_secret="g2-synthetic-cursor-secret"))
    monkeypatch.setattr(social.os, "urandom", lambda size: bytes(range(size)))
    query = social_query()
    assert social._decode_cursor(query) == (NOW, "post-g2")
    assert social._encode_cursor(query, created_at=NOW, item_id="post-g2") == SOCIAL_CURSOR
    encrypted = pagination.decode_cursor_bytes(SOCIAL_CURSOR)
    assert b"world-g2" not in encrypted
    assert b"wc-g2" not in encrypted
    assert b"post-g2" not in encrypted


@pytest.mark.parametrize("changes", [
    {"world_id": "other-world"}, {"world_character_id": "other-character"}, {"tab": "replies"},
])
def test_social_cursor_scope_remains_domain_specific(monkeypatch, changes):
    monkeypatch.setattr(social, "settings", SimpleNamespace(app_secret="g2-synthetic-cursor-secret"))
    with pytest.raises(WorldCharacterSocialProfileValidationError) as error:
        social._decode_cursor(replace(social_query(), **changes))
    assert error.value.reason_code == "world_character_social_profile_invalid_request"


def test_social_cursor_rejects_changed_ciphertext_and_wrong_secret(monkeypatch):
    monkeypatch.setattr(social, "settings", SimpleNamespace(app_secret="g2-synthetic-cursor-secret"))
    corrupted = bytearray(pagination.decode_cursor_bytes(SOCIAL_CURSOR))
    corrupted[20] ^= 1
    with pytest.raises(WorldCharacterSocialProfileValidationError):
        social._decode_cursor(replace(social_query(), cursor=pagination.encode_cursor_bytes(bytes(corrupted))))
    monkeypatch.setattr(social.settings, "app_secret", "g2-other-synthetic-secret")
    with pytest.raises(WorldCharacterSocialProfileValidationError):
        social._decode_cursor(social_query())


@pytest.mark.parametrize("payload,encoded", [
    (b"", ""), (b"a", "YQ"), (b"ab", "YWI"), (b"abc", "YWJj"), (b"\xff\x00\xfe", "_wD-"),
])
def test_cursor_byte_encoding_preserves_padding_and_binary_compatibility(payload, encoded):
    assert pagination.encode_cursor_bytes(payload) == encoded
    assert pagination.decode_cursor_bytes(encoded) == payload
    assert pagination.decode_cursor_bytes(encoded + "=" * (-len(encoded) % 4)) == payload
