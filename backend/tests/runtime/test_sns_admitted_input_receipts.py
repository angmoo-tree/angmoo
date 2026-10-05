"""Receipts describe admitted physical input, including omission and retry."""
import asyncio
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from app.providers.input_budget import InputBudgetError
from runtime.test_sns_budget_transport import runtime
from runtime.test_sns_model_input_budget import Counter


class OmitOneMemory(Counter):
    async def count(self, request, model):
        _, digest = await super().count(request, model)
        payload, _ = json.JSONDecoder().raw_decode(request.user_prompt)
        packets = payload["context"]["memories"]["optional"]["packets"]
        return (101 if packets else 42), digest


def memory_payload():
    return {"context": {"required": "current source", "memories": {
        "required": {"packets": [{"ref": "retained-packet"}]},
        "optional": {"packets": [{"ref": "omitted-packet"}]},
    }}}


def test_omitted_memory_is_absent_from_checkpoint_and_observer_receipts(monkeypatch, deny_external_network):
    async def scenario():
        events, receipts = [], []
        db, row, provider, adapter, _, _ = runtime(monkeypatch, count=OmitOneMemory(),
            responses=[{"ok": True}], observer=lambda kind, value: events.append((kind, value)))
        original = memory_payload()
        before = deepcopy(original)
        await provider.call(node="CombinedTargetSelector", lane="selector", system="s",
            payload=original, schema={}, validator=lambda value: value, max_tokens=8192,
            on_input_receipt=receipts.append)
        assert len(receipts) == len(adapter.requests) == 1
        assert receipts[0]["memory_packet_refs"] == ["retained-packet"]
        assert receipts[0]["omissions"] == {"today_activity": 0, "memory_packets": 1}
        manifests = [value for kind, value in events if kind == "input_manifest"]
        assert len(manifests) == 1
        assert manifests[0]["memory_packet_refs"] == ["retained-packet"]
        assert manifests[0]["input_chars"] == len(adapter.requests[0].system_prompt) + len(adapter.requests[0].user_prompt)
        assert original == before
        db.close()
    asyncio.run(scenario())


def test_rejected_input_has_no_delivered_receipt_or_manifest(monkeypatch, deny_external_network):
    class AlwaysOver(Counter):
        async def count(self, request, model):
            _, digest = await super().count(request, model)
            return 101, digest
    async def scenario():
        events, receipts = [], []
        db, row, provider, adapter, _, tracker = runtime(monkeypatch, count=AlwaysOver(),
            observer=lambda kind, value: events.append((kind, value)))
        with pytest.raises(InputBudgetError, match="activity_input_budget_exceeded"):
            await provider.call(node="CombinedTargetSelector", lane="selector", system="s",
                payload={"required": "oversized source"}, schema={}, validator=lambda value: value,
                max_tokens=8192, on_input_receipt=receipts.append)
        assert not adapter.requests and not tracker.calls
        assert not receipts
        assert not any(kind == "input_manifest" for kind, _ in events)
        db.close()
    asyncio.run(scenario())


def test_json_retry_hash_and_receipts_match_each_admitted_request(monkeypatch, deny_external_network):
    async def scenario():
        events, receipts = [], []
        db, row, provider, adapter, _, _ = runtime(monkeypatch, count=OmitOneMemory(),
            responses=[('{"incomplete":', "MAX_TOKENS"), {"ok": True}],
            observer=lambda kind, value: events.append((kind, value)))
        await provider.call(node="CombinedTargetSelector", lane="selector", system="s",
            payload=memory_payload(), schema={}, validator=lambda value: value,
            max_tokens=8192, recover_truncation=True, on_input_receipt=receipts.append)
        actual_hashes = [sha256((request.system_prompt + "\n" + request.user_prompt).encode()).hexdigest()
            for request in adapter.requests]
        for kind in ("json_attempt_input", "json_attempt"):
            observed = [value["input_sha256"] for event, value in events if event == kind]
            assert observed == actual_hashes
        assert len(receipts) == len(adapter.requests) == 2
        assert all(receipt["memory_packet_refs"] == ["retained-packet"] for receipt in receipts)
        assert [receipt["input_sha256"] for receipt in receipts] == [
            sha256(request.user_prompt.encode()).hexdigest() for request in adapter.requests]
        assert adapter.requests[0].user_prompt != adapter.requests[1].user_prompt
        db.close()
    asyncio.run(scenario())
