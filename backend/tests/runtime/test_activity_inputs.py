"""Actual request boundaries retain newest whole records without changing sources."""
import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
import json

import pytest

from app.runtime.autonomous_activity import inputs, provider


@pytest.mark.parametrize("count", [0, 1, 12, 13, 20])
def test_shared_input_keeps_latest_records_and_counts_omissions(monkeypatch, count):
    @dataclass
    class Today:
        records: list

    # Equal timestamps preserve the domain reader's deterministic record-key order.
    original = [{"record_key": str(i), "occurred_at": "2026-09-25T12:00:00+00:00"}
                for i in range(count, 0, -1)]
    monkeypatch.setattr(inputs, "today_social_activity_reader", lambda _: SimpleNamespace(
        read=lambda **kwargs: Today(original)))
    monkeypatch.setattr(inputs, "read_state", lambda *args, **kwargs: {"confirmed_at": None})
    ctx = SimpleNamespace(db=None, user_id="owner", character=SimpleNamespace(
        name="A", persona_summary="", personality="", speech_style="", worldview="",
        topic_preferences=[], safety_rules=[]))
    value = inputs.shared_input(ctx, SimpleNamespace(id="actor", world_id="world", local_profile={}),
                                SimpleNamespace(timezone="Asia/Seoul", name="World", tagline=""))
    assert value["today_activity"]["records"] == original[:12]
    assert value["today_activity"].get("omitted_records", 0) == max(0, count - 12)
    assert len(original) == count


@pytest.mark.parametrize("nested", [True, False])
def test_transmitted_budget_drops_oldest_whole_record(monkeypatch, nested):
    monkeypatch.setattr(provider, "_api_key", lambda _: "test")
    monkeypatch.setattr(provider, "_llm_context", lambda *args, **kwargs: None)
    requests, receipts = [], []
    async def generate(**kwargs):
        requests.append(json.loads(kwargs["user_prompt"]))
        return {}
    monkeypatch.setattr(provider, "generate_json", generate)
    records = [{"record_key": "new", "body": "Do not do it. " + "n" * 33000},
               {"record_key": "old", "body": "o" * 33000}]
    context = {"today_activity": {"records": records, "omitted_records": 8}, "memories": {}}
    payload = {"context": context, "inbox": {}, "feed": {}} if nested else context
    actor = provider.ActivityProvider(SimpleNamespace(generation_thinking_level=None,
                                                      on_rate_limit_wait=None), None)
    async def scenario():
        for _ in range(2):
            await actor.call(node="test", lane="parent", system="rules", payload=payload,
                             schema={}, validator=lambda x: x, max_tokens=100,
                             on_input_receipt=receipts.append)
    asyncio.run(scenario())
    for request, receipt in zip(requests, receipts):
        sent = request["context"] if nested else request
        assert sent["today_activity"]["records"] == [records[0]]
        assert sent["today_activity"]["omitted_records"] == 8
        assert receipt["omissions"]["today_activity"] == 1
    assert len(records) == 2
