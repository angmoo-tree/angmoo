"""A successful trickle cannot extend model/count admission indefinitely."""
import asyncio
import json

import httpx
import pytest

from app.integrations import gemini_input_budget
from app.providers.input_budget import InputBudgetError
from runtime.test_sns_model_input_budget import profile, request


class SlowTrickle(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = json.dumps(body).encode()
        self.closed = False

    async def __aiter__(self):
        for _ in range(6):
            await asyncio.sleep(0.01)
            yield b" "
        yield self.body

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("operation", ["profile", "count"])
def test_admission_http_has_total_deadline_even_with_regular_chunks(monkeypatch, deny_external_network, operation):
    monkeypatch.setattr(gemini_input_budget, "REQUEST_TIMEOUT_SECONDS", 0.025, raising=False)
    body = {"totalTokens": 42} if operation == "count" else {
        "name": "models/" + request().model, "version": "001", "inputTokenLimit": 100,
        "outputTokenLimit": 16384, "supportedGenerationMethods": ["generateContent"]}
    stream = SlowTrickle(body)
    calls = []
    def respond(value):
        calls.append(value)
        return httpx.Response(200, stream=stream)
    async def scenario():
        port = gemini_input_budget.GeminiModelTokenCounter(transport=httpx.MockTransport(respond))
        with pytest.raises(InputBudgetError, match="activity_input_budget_unavailable"):
            if operation == "count":
                await port.count(request(), profile())
            else:
                await port.profile(request())
    asyncio.run(scenario())
    assert len(calls) == 1 and stream.closed
