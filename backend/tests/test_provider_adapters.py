from __future__ import annotations

import asyncio

import pytest

from app.providers.contracts import (
    EmbeddingRequest,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from app.providers.fake import FakeProviderAdapter
from app.providers.gemini import GeminiAdapter
from app.providers.registry import get_model_spec, normalize_provider_name


def _request(*, api_key: str = "synthetic-provider-secret") -> ProviderRequest:
    return ProviderRequest(
        api_key=api_key,
        model="gemini-3.1-flash-lite",
        system_prompt="system",
        user_prompt="user",
        max_output_tokens=64,
        timeout_seconds=1.0,
    )


def test_provider_request_repr_redacts_api_key() -> None:
    request = _request()

    assert request.api_key not in repr(request)


def test_registry_normalizes_gemini_alias_and_capabilities() -> None:
    assert normalize_provider_name("Gemini") == "google"
    spec = get_model_spec("google-generative-ai", "gemini-3.1-flash-lite")

    assert spec.provider == "google"
    assert spec.capabilities.text is True
    assert spec.capabilities.structured_json is True
    assert spec.capabilities.image_input is True
    assert spec.capabilities.embedding is False


def test_fake_provider_success_and_embedding_are_network_free() -> None:
    adapter = FakeProviderAdapter()

    async def run() -> tuple[ProviderResponse, ProviderResponse, list[float]]:
        return (
            await adapter.generate_text(_request()),
            await adapter.generate_json(_request()),
            await adapter.embed(
                EmbeddingRequest(
                    api_key="synthetic-provider-secret",
                    model="gemini-embedding-2",
                    text="hello",
                    output_dimension=3,
                )
            ),
        )

    text_response, json_response, embedding = asyncio.run(run())

    assert text_response.text == "fake provider response"
    assert json_response.parsed == {
        "status": "ok",
        "model": "gemini-3.1-flash-lite",
    }
    assert embedding == [0.0, 0.0, 0.0]


def test_fake_provider_invalid_json_scenario() -> None:
    response = asyncio.run(
        FakeProviderAdapter("invalid_json").generate_json(_request())
    )

    assert response.text == "{invalid-json"
    assert response.parsed is None


@pytest.mark.parametrize(
    ("scenario", "error_type", "retryable"),
    [
        ("timeout", TimeoutError, None),
        ("rate_limit", ProviderError, True),
        ("unsupported", ProviderError, False),
    ],
)
def test_fake_provider_failure_scenarios(
    scenario: str,
    error_type: type[BaseException],
    retryable: bool | None,
) -> None:
    with pytest.raises(error_type) as exc_info:
        asyncio.run(FakeProviderAdapter(scenario).generate_text(_request()))

    if retryable is not None:
        assert isinstance(exc_info.value, ProviderError)
        assert exc_info.value.retryable is retryable


def test_gemini_error_normalization_redacts_exact_secret() -> None:
    secret = "synthetic-provider-secret"

    error = GeminiAdapter().normalize_error(
        RuntimeError(f"request failed with {secret}"),
        api_key=secret,
    )

    assert secret not in str(error)
    assert "[REDACTED]" in str(error)
