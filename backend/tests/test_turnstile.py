import json
from urllib.error import URLError

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services import turnstile


class _Response:
    def __init__(self, payload: dict[str, object] | str) -> None:
        self.payload = (
            payload.encode("utf-8")
            if isinstance(payload, str)
            else json.dumps(payload).encode("utf-8")
        )
        self.offset = 0
        self.headers: dict[str, str] = {}
        self.read_sizes: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            size = len(self.payload) - self.offset
        start = self.offset
        self.offset = min(len(self.payload), self.offset + size)
        return self.payload[start : self.offset]


def _enable_turnstile(monkeypatch, *, secret: str | None = "secret-test") -> None:
    monkeypatch.setattr(settings, "TURNSTILE_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "TURNSTILE_SECRET_KEY",
        SecretStr(secret) if secret is not None else None,
    )
    monkeypatch.setattr(settings, "TURNSTILE_TIMEOUT_SECONDS", 5.0)


def test_disabled_allows_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TURNSTILE_ENABLED", False)

    turnstile.verify_turnstile_or_raise(None)


def test_enabled_rejects_missing_token(monkeypatch) -> None:
    _enable_turnstile(monkeypatch)

    with pytest.raises(turnstile.TurnstileVerificationError):
        turnstile.verify_turnstile_or_raise(None)


def test_enabled_rejects_oversized_token(monkeypatch) -> None:
    _enable_turnstile(monkeypatch)

    with pytest.raises(turnstile.TurnstileVerificationError):
        turnstile.verify_turnstile_or_raise("x" * 2049)


def test_enabled_rejects_missing_secret(monkeypatch) -> None:
    _enable_turnstile(monkeypatch, secret=None)

    with pytest.raises(turnstile.TurnstileConfigError):
        turnstile.verify_turnstile_or_raise("token-test")


def test_siteverify_success_allows(monkeypatch) -> None:
    _enable_turnstile(monkeypatch)

    def fake_urlopen(request, timeout):
        assert timeout == 5.0
        body = request.data.decode("utf-8")
        assert "secret=secret-test" in body
        assert "response=token-test" in body
        return _Response({"success": True})

    monkeypatch.setattr(turnstile, "urlopen", fake_urlopen)

    turnstile.verify_turnstile_or_raise("token-test")


def test_siteverify_failure_rejects_without_logging_secrets(monkeypatch, caplog) -> None:
    _enable_turnstile(monkeypatch, secret="secret-private")
    caplog.set_level("INFO", logger=turnstile.__name__)

    def fake_urlopen(request, timeout):
        return _Response({"success": False, "error-codes": ["invalid-input-response"]})

    monkeypatch.setattr(turnstile, "urlopen", fake_urlopen)

    with pytest.raises(turnstile.TurnstileVerificationError):
        turnstile.verify_turnstile_or_raise("token-private")

    log_text = caplog.text
    assert "invalid-input-response" in log_text
    assert "token-private" not in log_text
    assert "secret-private" not in log_text


def test_siteverify_network_error_is_unavailable(monkeypatch) -> None:
    _enable_turnstile(monkeypatch)

    def fake_urlopen(request, timeout):
        raise URLError("offline")

    monkeypatch.setattr(turnstile, "urlopen", fake_urlopen)

    with pytest.raises(turnstile.TurnstileUnavailableError):
        turnstile.verify_turnstile_or_raise("token-test")


def test_siteverify_timeout_is_unavailable(monkeypatch) -> None:
    _enable_turnstile(monkeypatch)

    def fake_urlopen(request, timeout):
        raise TimeoutError("slow")

    monkeypatch.setattr(turnstile, "urlopen", fake_urlopen)

    with pytest.raises(turnstile.TurnstileUnavailableError):
        turnstile.verify_turnstile_or_raise("token-test")


def test_siteverify_invalid_json_is_unavailable(monkeypatch) -> None:
    _enable_turnstile(monkeypatch)

    def fake_urlopen(request, timeout):
        return _Response("not-json")

    monkeypatch.setattr(turnstile, "urlopen", fake_urlopen)

    with pytest.raises(turnstile.TurnstileUnavailableError):
        turnstile.verify_turnstile_or_raise("token-test")


def test_siteverify_oversized_content_length_fails_closed(monkeypatch) -> None:
    _enable_turnstile(monkeypatch)
    response = _Response({"success": True})
    response.headers["Content-Length"] = str(turnstile.TURNSTILE_MAX_RESPONSE_BYTES + 1)
    monkeypatch.setattr(turnstile, "urlopen", lambda *_args, **_kwargs: response)

    with pytest.raises(turnstile.TurnstileUnavailableError):
        turnstile.verify_turnstile_or_raise("token-test")

    assert response.read_sizes == []


def test_siteverify_chunked_oversized_body_fails_closed_without_unbounded_read(
    monkeypatch,
) -> None:
    _enable_turnstile(monkeypatch)
    response = _Response("x" * (turnstile.TURNSTILE_MAX_RESPONSE_BYTES + 1))
    monkeypatch.setattr(turnstile, "urlopen", lambda *_args, **_kwargs: response)

    with pytest.raises(turnstile.TurnstileUnavailableError):
        turnstile.verify_turnstile_or_raise("token-test")

    assert response.read_sizes
    assert -1 not in response.read_sizes
    assert sum(response.read_sizes) <= turnstile.TURNSTILE_MAX_RESPONSE_BYTES + 1
