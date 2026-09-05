from __future__ import annotations

import asyncio
import json
import logging

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.core.redaction import redact_exact_secret_text, redact_exact_secrets
from app.credentials import CredentialMaterial, CredentialPurpose
from app.providers.contracts import (
    EmbeddingRequest,
    ProviderCapabilities,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from app.providers.fake import FakeProviderAdapter
from app.providers.gemini import GeminiAdapter
from app.services import (direct_llm)
from app.runtime.characters import creator as agent_creation_drafts
from app.main import app


def _canary() -> str:
    return "m3_canary_7f9d2a4c1b6e_secret"


def _context(canary: str) -> direct_llm.DirectLlmCallContext:
    return direct_llm.DirectLlmCallContext(
        credential_id="credential-m3",
        key_fingerprint="fingerprint-m3",
        character_id="character-m3",
        agent_run_id="run-m3",
        node="m3-security",
        lane=canary[-8:],
        provider="google",
        model="gemini-test",
    )


def _request(canary: str) -> ProviderRequest:
    return ProviderRequest(
        api_key=canary,
        model="gemini-test",
        system_prompt="system",
        user_prompt="user",
        max_output_tokens=32,
        timeout_seconds=1,
    )


def test_exact_secret_redaction_handles_arbitrary_nested_canary() -> None:
    canary = _canary()
    payload = {"message": f"failed {canary}", "items": [canary]}

    assert canary not in redact_exact_secret_text(str(payload), canary)
    assert canary not in json.dumps(redact_exact_secrets(payload, canary))


def test_secret_wrappers_and_provider_requests_have_safe_repr() -> None:
    canary = _canary()
    material = CredentialMaterial(
        credential_id="credential-m3",
        provider="google",
        model="gemini-test",
        fingerprint="fingerprint-m3",
        purpose=CredentialPurpose.RESIDENT_LLM,
        _secret=canary,
    )
    embedding = EmbeddingRequest(
        api_key=canary,
        model="embedding-test",
        text="safe text",
        output_dimension=4,
    )

    for value in (material, _request(canary), embedding):
        assert canary not in str(value)
        assert canary not in repr(value)


def test_openapi_never_exposes_encrypted_envelope_storage_fields() -> None:
    encoded = json.dumps(app.openapi(), sort_keys=True)

    for forbidden in (
        "encrypted_api_key",
        "encrypted_pollinations_api_key",
        "encrypted_replicate_api_token",
        "ciphertext",
    ):
        assert forbidden not in encoded


@pytest.mark.parametrize("adapter", [GeminiAdapter(), FakeProviderAdapter()])
def test_provider_error_normalization_redacts_exact_canary(adapter) -> None:
    canary = _canary()
    error = adapter.normalize_error(RuntimeError(f"failed {canary}"), api_key=canary)

    assert canary not in str(error)


def test_fake_provider_redacts_existing_provider_error() -> None:
    canary = _canary()
    error = FakeProviderAdapter().normalize_error(
        ProviderError(
            f"rate limit {canary}",
            failure_class="rate_limit",
            provider_code=429,
            retryable=True,
        ),
        api_key=canary,
    )

    assert canary not in str(error)
    assert error.provider_code == 429
    assert error.retryable is True


def test_direct_llm_exception_log_and_tracker_do_not_contain_exact_canary(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = _canary()

    class FailingAdapter:
        capabilities = ProviderCapabilities(text=True)

        async def generate_text(self, request: ProviderRequest):
            raise RuntimeError(f"provider echoed {request.api_key}")

        async def generate_json(self, request: ProviderRequest):
            return await self.generate_text(request)

        def normalize_error(self, exc, *, api_key=None):
            return FakeProviderAdapter().normalize_error(exc, api_key=api_key)

    monkeypatch.setattr(direct_llm, "get_provider_adapter", lambda *_: FailingAdapter())
    tracker = direct_llm.RunLlmTracker(max_calls=2)
    caplog.set_level(logging.WARNING)

    with pytest.raises(direct_llm.DirectLlmError) as exc_info:
        asyncio.run(
            direct_llm.generate_text(
                api_key=canary,
                context=_context(canary),
                tracker=tracker,
                system_prompt="system",
                user_prompt="user",
                timeout_seconds=1,
            )
        )

    evidence = json.dumps(tracker.summary(), default=str) + caplog.text + str(
        exc_info.value
    )
    assert canary not in evidence


def test_invalid_json_diagnostics_do_not_store_exact_canary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = _canary()

    class InvalidJsonAdapter:
        capabilities = ProviderCapabilities(text=True, structured_json=True)

        async def generate_text(self, request: ProviderRequest):
            return await self.generate_json(request)

        async def generate_json(self, request: ProviderRequest):
            return ProviderResponse(
                text=f'{{"leak":"{request.api_key}"',
                parsed=None,
                usage=ProviderUsage(),
            )

        def normalize_error(self, exc, *, api_key=None):
            return FakeProviderAdapter().normalize_error(exc, api_key=api_key)

    monkeypatch.setattr(
        direct_llm, "get_provider_adapter", lambda *_: InvalidJsonAdapter()
    )
    tracker = direct_llm.RunLlmTracker(max_calls=3)

    with pytest.raises(direct_llm.DirectLlmJsonError) as exc_info:
        asyncio.run(
            direct_llm.generate_json(
                api_key=canary,
                context=_context(canary),
                tracker=tracker,
                system_prompt="system",
                user_prompt="user",
                response_schema={"type": "object"},
                timeout_seconds=1,
            )
        )

    evidence = json.dumps(tracker.summary(), default=str) + str(exc_info.value)
    assert canary not in evidence
    assert "[REDACTED]" in evidence


def test_draft_pollinations_key_is_authorization_only_not_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = _canary()
    captured: dict[str, str | None] = {}

    class Response:
        headers = {"Content-Type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size: int = -1) -> bytes:
            del size
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return b"synthetic-image"

    def fake_urlopen(request, _timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        return Response()

    monkeypatch.setattr(settings, "POLLINATIONS_API_KEY", SecretStr(canary))
    monkeypatch.setattr(
        agent_creation_drafts,
        "_open_pollinations_request",
        fake_urlopen,
    )
    monkeypatch.setattr(
        agent_creation_drafts.profile_media,
        "validate_profile_media_content",
        lambda *_args: None,
    )

    agent_creation_drafts._download_pollinations_image(
        model="flux",
        prompt="safe prompt",
        media_type="avatar",
        seed=7,
    )

    assert canary not in str(captured["url"])
    assert captured["authorization"] == f"Bearer {canary}"
