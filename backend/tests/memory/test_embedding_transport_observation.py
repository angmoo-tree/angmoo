"""Independent MockTransport counts versus hooks below the pinned SDK."""
import asyncio
import json
import pytest
from app.core import work_observation as observation
from app.providers.gemini import GeminiAdapter
from app.providers.contracts import EmbeddingBatchRequest, EmbeddingRequest, ProviderError
from memory.test_embedding_batch_transport import transport


@pytest.fixture
def events():
    rows=[];remove=observation.install(rows.append)
    try:yield rows
    finally:remove()


@pytest.mark.parametrize("count",[1,7,20])
def test_independent_attempt_and_response_alignment(transport,events,count):
    texts=tuple(f"PRIVATE-SENTINEL {i}" for i in range(count))
    with observation.scope(world_id="w",actor_id="a",batch_id="batch",purpose="document_incremental"):
        result=asyncio.run(GeminiAdapter().embed_batch_measured(EmbeddingBatchRequest("SECRET-KEY","gemini-embedding-2",texts,768),timeout_seconds=30))
    attempts=[e for e in events if e.get("boundary")=="attempt_start"]
    assert len(attempts)==len(transport[0])==1
    assert attempts[0]["batch_id"]=="batch" and attempts[0]["input_count"]==count
    assert [v[0] for v in result.vectors]==list(range(1,count+1))
    assert any(e.get("response_count")==count and e.get("dimension")==768 for e in events)
    assert "PRIVATE" not in json.dumps(events) and "SECRET" not in json.dumps(events)


@pytest.mark.parametrize("kind",["503","timeout","short","extra","dimension","nan","inf"])
def test_invalid_responses_and_timeout_never_manufacture_retries(transport,events,kind):
    transport[1]["kind"]=kind
    with pytest.raises(ProviderError):
        asyncio.run(GeminiAdapter().embed_batch_measured(EmbeddingBatchRequest("secret","gemini-embedding-2",("a","b"),768),timeout_seconds=30))
    assert len(transport[0])==len([e for e in events if e.get("boundary")=="attempt_start"])==1
    assert not any(e.get("boundary")=="response_validated" for e in events)
    assert len([e for e in events if e.get("boundary")=="logical_end"])==1


@pytest.mark.parametrize("texts",[tuple("x" for _ in range(21)),("x"*8193,),tuple("가"*2000 for _ in range(20))])
def test_local_rejection_makes_zero_physical_attempts(transport,events,texts):
    with pytest.raises((ProviderError,ValueError)):
        asyncio.run(GeminiAdapter().embed_batch_measured(EmbeddingBatchRequest("secret","gemini-embedding-2",texts,768),timeout_seconds=30))
    assert not transport[0] and not any(e.get("boundary")=="attempt_start" for e in events)


def test_query_and_unsupported_transport_are_distinguished(transport,events,monkeypatch):
    with observation.scope(world_id="w",actor_id="a",purpose="query"):
        asyncio.run(GeminiAdapter().embed_measured(EmbeddingRequest("secret","gemini-embedding-2","query",768),timeout_seconds=30))
    assert len(transport[0])==1 and all(e["purpose"]=="query" for e in events)
    monkeypatch.setattr("app.providers.embedding_observation.find_spec",lambda _:object())
    events.clear()
    asyncio.run(GeminiAdapter().embed_measured(EmbeddingRequest("secret","gemini-embedding-2","query",768),timeout_seconds=30))
    assert len(transport[0])==2
    assert any(e.get("transport_observable") is False for e in events)
    assert not any(e.get("boundary")=="attempt_start" for e in events)
