"""Exercise the installed SDK's HTTPX2 boundary without external requests."""
import asyncio
from dataclasses import replace

import httpx2
import pytest
from google import genai
from app.providers.gemini import GeminiAdapter, classify_generation_failure
from test_provider_adapters import _request


@pytest.mark.parametrize("failure", [None, "timeout", "network", 429, 503])
def test_actual_sdk_preserves_api_retry_and_error_contract(monkeypatch, failure):
    calls = []
    original = genai.Client

    def handler(request):
        calls.append(request)
        assert request.url.path.startswith("/v1beta/")
        if failure == "timeout":
            raise httpx2.ReadTimeout("private payload")
        if failure == "network":
            raise httpx2.ConnectError("private key")
        if failure:
            return httpx2.Response(failure, json={"error": {"code": failure, "message": "private"}})
        return httpx2.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]})

    def client(**kwargs):
        options = kwargs["http_options"]
        options.client_args = {"transport": httpx2.MockTransport(handler)}
        return original(**kwargs)

    monkeypatch.setattr(genai, "Client", client)
    request = replace(_request(), sdk_attempts=1)
    if failure is None:
        assert asyncio.run(GeminiAdapter().generate_text(request)).text == "ok"
    else:
        with pytest.raises(Exception) as error:
            asyncio.run(GeminiAdapter().generate_text(request))
        normalized = classify_generation_failure(error.value)
        assert normalized.retryable and "private" not in str(normalized)
        expected = {"timeout": "timeout", "network": "transport_failed", 429: "rate_limited", 503: "provider_unavailable"}
        assert normalized.failure_class == expected[failure]
    assert len(calls) == 1
