import asyncio
from types import SimpleNamespace

import pytest

from app.runtime.autonomous_activity.combined_selection import CombinedSelection
from app.runtime.autonomous_activity.contracts import Candidate


@pytest.mark.parametrize("counts,expected", [((0, 0), []), ((1, 1), []), ((2, 1), ["inbox"]),
    ((1, 2), ["feed"]), ((2, 2), ["combined"])])
def test_selection_bypass_and_shared_call_counts(counts, expected):
    async def scenario():
        calls = []
        prepared = {lane: {"candidates": [Candidate(target_id=str(i), text="source", allowed_actions=["like"]).model_dump()
            for i in range(count)]} for lane, count in zip(("inbox", "feed"), counts)}
        async def guard(_): return {}
        async def error(exc): raise exc
        def adapter(lane):
            async def select(state):
                calls.append(lane)
                return {"selections": [{"target_id": "0"}]}
            async def call(**kwargs):
                calls.append("combined")
                assert set(kwargs["payload"]["lanes"]) == {"inbox", "feed"}
                return kwargs["validator"]({k: {"selections": [{"target_id": "0", "memory_query": k}]} for k in prepared})
            return SimpleNamespace(select=select, provider=SimpleNamespace(call=call), delivery=lambda _: None)
        selection = CombinedSelection({k: adapter(k) for k in prepared},
            {k: SimpleNamespace(guard=guard, on_error=error) for k in prepared})
        state = {"identity": {}, "shared_context": {}, "prepared_lanes": prepared, "selection_mode": "combined"}
        result = await selection.select(state)
        assert calls == expected
        for lane, count in zip(("inbox", "feed"), counts):
            assert len(result["prepared_lanes"][lane]["selections"]) == (1 if count else 0)
    asyncio.run(scenario())


def test_invalid_inbox_selection_does_not_discard_valid_feed():
    async def scenario():
        candidates = [Candidate(target_id=str(i), text="source", allowed_actions=["like"]).model_dump() for i in range(2)]
        async def guard(_): return {}
        async def error(exc): raise exc
        async def call(**kwargs):
            return kwargs["validator"]({"inbox": {"selections": [{"target_id": "not-supplied"}]},
                "feed": {"selections": [{"target_id": "0", "memory_query": "x" * 401}]}})
        selection = CombinedSelection({lane: SimpleNamespace(provider=SimpleNamespace(call=call), delivery=lambda _: None)
            for lane in ("inbox", "feed")}, {lane: SimpleNamespace(guard=guard, on_error=error) for lane in ("inbox", "feed")})
        result = await selection.select({"identity": {}, "shared_context": {}, "selection_mode": "combined",
            "prepared_lanes": {lane: {"candidates": candidates} for lane in ("inbox", "feed")}})
        assert result["prepared_lanes"]["inbox"]["preparation_error"]["reason"] == "selection_invalid"
        assert result["prepared_lanes"]["feed"]["selections"][0]["target_id"] == "0"
    asyncio.run(scenario())
