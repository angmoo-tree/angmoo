import asyncio
import json
import httpx
import pytest
from google import genai
from google.genai import types
from app.providers.gemini import GeminiAdapter
from app.providers.contracts import EmbeddingBatchRequest, EmbeddingRequest, ProviderError
from app.providers.gemini_embedding_batch import batch_fits


@pytest.fixture
def transport(monkeypatch):
    calls = []
    behavior = {"kind": "valid"}
    original = genai.Client
    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        count = len(body["requests"])
        if behavior["kind"] == "short":
            count -= 1
        if behavior["kind"] == "timeout":
            raise httpx.ReadTimeout("secret")
        if behavior["kind"] == "503":
            return httpx.Response(503, json={"error": {"code": 503, "message": "secret", "status": "UNAVAILABLE"}})
        embeddings = [{"values": [float(i+1)] + [0.] * 767} for i in range(count)]
        if behavior["kind"] == "extra":
            embeddings.append(embeddings[0])
        if behavior["kind"] in {"empty", "dimension", "nan", "inf"}:
            embeddings[0]["values"] = {"empty": [], "dimension": [1.],
                "nan": [float("nan")] + [0.] * 767, "inf": [float("inf")] + [0.] * 767}[behavior["kind"]]
        return httpx.Response(200, content=json.dumps({"embeddings": embeddings}), headers={"content-type": "application/json"})
    def client(**kwargs):
        options = kwargs.pop("http_options")
        options.async_client_args = {"transport": httpx.MockTransport(handler)}
        return original(**kwargs, http_options=options)
    monkeypatch.setattr(genai, "Client", client)
    return calls, behavior


@pytest.mark.parametrize("count", [1, 10, 20])
def test_actual_pinned_sdk_sends_one_http_and_independent_contents(transport, count):
    calls, _ = transport
    texts = tuple(f"title: Memory | text: independent {i}" for i in range(count))
    response = asyncio.run(GeminiAdapter().embed_batch_measured(
        EmbeddingBatchRequest("synthetic", "gemini-embedding-2", texts, 768), timeout_seconds=30))
    assert len(calls) == 1
    assert calls[0].url.path.endswith(":batchEmbedContents")
    requests = json.loads(calls[0].content)["requests"]
    assert [entry["content"]["parts"][0]["text"] for entry in requests] == list(texts)
    assert all(len(entry["content"]["parts"]) == 1 for entry in requests)
    assert [v[0] for v in response.vectors] == list(range(1,count+1))
    assert response.physical_attempts == 1 and response.usage.total_tokens is None


@pytest.mark.parametrize("kind", ["short", "extra", "empty", "dimension", "nan", "inf", "timeout", "503"])
def test_invalid_response_does_not_resubmit_or_fallback(transport, kind):
    calls, behavior = transport
    behavior["kind"] = kind
    with pytest.raises(ProviderError) as error:
        asyncio.run(GeminiAdapter().embed_batch_measured(EmbeddingBatchRequest(
            "synthetic", "gemini-embedding-2", ("a", "b"), 768), timeout_seconds=30))
    assert len(calls) == 1 and error.value.physical_attempts == 1
    assert "secret" not in str(error.value)


def test_limits_and_single_query_contract(transport):
    assert not batch_fits(()) and not batch_fits(tuple("x" for _ in range(21)))
    assert not batch_fits(("x" * 8193,))
    assert not batch_fits(tuple("가" * 2000 for _ in range(20)))
    response = asyncio.run(GeminiAdapter().embed_measured(EmbeddingRequest(
        "synthetic", "gemini-embedding-2", "task: search result | query: a", 768), timeout_seconds=30))
    assert len(response.vector) == 768 and response.physical_attempts == 1
    assert len(transport[0]) == 1
