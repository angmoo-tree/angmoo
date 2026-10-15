import asyncio
import json
import httpx
import pytest

from app.domains.media.generation_contracts import ImageSubmissionError
from app.domains.media.schemas import diagnostic_projection
from app.integrations.image_api import ImageHttp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("error,category", [(httpx.ConnectTimeout, "connect_timeout"),
    (httpx.ReadTimeout, "read_timeout"), (httpx.WriteTimeout, "write_timeout"),
    (httpx.PoolTimeout, "pool_timeout"), (httpx.ConnectError, "connect_error"),
    (httpx.ReadError, "read_error"), (httpx.WriteError, "write_error"),
    (httpx.RemoteProtocolError, "remote_protocol_error")])
async def test_transport_is_typed_without_payload_or_automatic_resubmission(error, category):
    calls = []
    def handler(request):
        calls.append(request)
        raise error("SECRET prompt signed-url https://sensitive.invalid/?key=SECRET")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ImageSubmissionError) as caught:
            await ImageHttp(client).request("POST", "https://example.invalid/images", key="SECRET",
                json={"prompt": "PRIVATE"}, diagnostic_provider="openrouter")
    assert len(calls) == 1 and calls[0].extensions["timeout"]["read"] == 120
    assert caught.value.outcome_unknown is True
    assert str(caught.value) == "provider_transport_error"
    value = diagnostic_projection(json.dumps(caught.value.diagnostic))
    assert value["transport"]["category"] == category
    assert value["transport"]["observed_phase"] == "request_started"
    assert "status" not in value["transport"]
    assert not any(word in json.dumps(value) for word in ("SECRET", "PRIVATE", "sensitive"))


@pytest.mark.anyio
async def test_error_response_allowlist_and_legacy_consumers():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(502, headers={"x-request-id": "gen-123-Abcdefgh123", "authorization": "SECRET"},
            json={"error": {"code": 502, "message": "SECRET PRIVATE", "metadata": {"raw": "PRIVATE"}}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ImageSubmissionError) as caught:
            await ImageHttp(client).request("POST", "https://example.invalid/images", diagnostic_provider="openrouter")
        value = diagnostic_projection(caught.value.diagnostic)
        assert value["transport"]["status"] == 502
        assert value["transport"]["provider_code"] == "502"
        assert value["transport"]["request_id"] == "gen-123-Abcdefgh123"
        assert "PRIVATE" not in json.dumps(value)
        # ComfyUI explicitly asks to parse its own bounded error envelope.
        response = await ImageHttp(client).request("POST", "https://example.invalid/prompt", error_body_limit=4096)
        assert response.status_code == 502 and response.json()["error"]["code"] == 502
        with pytest.raises(ImageSubmissionError) as old:
            await ImageHttp(client).request("GET", "https://example.invalid/discovery")
        assert old.value.diagnostic is None
    assert len(calls) == 3
    assert diagnostic_projection({"kind": "error", "stage": "execution", "messages": [{"node_id": "4"}]})["messages"][0]["node_id"] == "4"


class ErrorBody(httpx.AsyncByteStream):
    def __init__(self, mode):
        self.mode = mode
    async def __aiter__(self):
        if self.mode == "slow":
            await asyncio.Event().wait()
        if self.mode == "broken":
            raise httpx.ReadError("SECRET")
        if self.mode == "cancel":
            raise asyncio.CancelledError
        yield b"x" * (20000 if self.mode == "large" else 4)


@pytest.mark.anyio
@pytest.mark.parametrize("mode,state", [("slow", "time_budget"), ("broken", "body_read_failed"),
    ("large", "truncated"), ("json", "non_json")])
async def test_diagnostic_failure_keeps_original_502(monkeypatch, mode, state):
    monkeypatch.setattr("app.integrations.image_http_diagnostics.ERROR_SECONDS", .02)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(502, stream=ErrorBody(mode)))) as client:
        with pytest.raises(ImageSubmissionError) as caught:
            await ImageHttp(client).request("POST", "https://example.invalid/images", diagnostic_provider="openrouter")
    assert str(caught.value) == "provider_http_502"
    assert caught.value.diagnostic["transport"]["completeness"] == state


@pytest.mark.anyio
async def test_actual_cancellation_not_converted_to_diagnostic():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(502, stream=ErrorBody("cancel")))) as client:
        with pytest.raises(asyncio.CancelledError):
            await ImageHttp(client).request("POST", "https://example.invalid/images", diagnostic_provider="openrouter")


def test_strict_diagnostic_rejects_unbounded_or_secret_fields():
    assert diagnostic_projection({"kind": "error", "stage": "submission", "messages": [], "raw_body": "secret"}) is None
    assert diagnostic_projection({"kind": "error", "stage": "submission", "messages": [{"message": "x" * 20000}]}) is None


@pytest.mark.anyio
async def test_success_http_timing_and_discovery_do_not_imply_generation():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []}))) as client:
        response = await ImageHttp(client).request("POST", "https://example.invalid/images", diagnostic_provider="openrouter")
        value = diagnostic_projection(response.extensions["angmoo_http_validation_diagnostic"])
        elapsed = value["transport"]["elapsed_ms"]
        await asyncio.sleep(.01)
        assert value["transport"]["elapsed_ms"] == elapsed
        assert value["transport"]["observed_phase"] == "result_validation"
        assert value["transport"]["status"] == 200
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
        with pytest.raises(ImageSubmissionError) as failed:
            await ImageHttp(client).request("GET", "https://example.invalid/discovery", diagnostic_provider="openrouter", diagnostic_purpose="discovery")
        assert failed.value.outcome_unknown is False
        assert failed.value.diagnostic["transport"]["purpose"] == "discovery"
