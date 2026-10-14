import asyncio
from types import SimpleNamespace

import pytest

from app.runtime.autonomous_activity.combined_selection import CombinedSelection
from app.runtime.autonomous_activity.contracts import Candidate


@pytest.mark.parametrize("invalid_lane,submitted,shared", [("inbox", False, False), ("feed", False, False), ("inbox", True, False), ("feed", False, True)])
def test_final_guard_invalidates_only_unsubmitted_independent_lane(invalid_lane, submitted, shared):
    from app.runtime.autonomous_activity.inputs import ActivityRelationshipValidationError
    from app.domains.relationships.contracts.social_context import SocialContextValidationError
    async def scenario():
        invalid = False
        calls = []
        candidates = [Candidate(target_id=str(i), text="source", allowed_actions=["like"]).model_dump() for i in range(2)]
        def port(lane):
            async def guard(_):
                if invalid and lane == invalid_lane:
                    original = SocialContextValidationError("visibility_lost", failure_scope="shared" if shared else "lane")
                    raise ActivityRelationshipValidationError(original.reason, lane=lane, original=original)
            async def error(exc):
                return {"path": lane, "status": "failed", "reason": exc.reason, "public_action_count": 0}
            return SimpleNamespace(guard=guard, on_error=error)
        ports = {lane: port(lane) for lane in ("inbox", "feed")}
        async def call(**kwargs):
            nonlocal invalid
            if submitted:
                await kwargs["before_provider_request"](0)
                kwargs["on_submission"]()
                calls.append("combined")
            invalid = True
            await kwargs["before_json_retry" if submitted else "before_provider_request"](1 if submitted else 0)
            pytest.fail("invalid frozen request was submitted")
        def adapter(lane):
            async def select(state):
                await ports[lane].guard(state)
                calls.append(lane)
                return {"selections": [{"target_id": "0"}]}
            return SimpleNamespace(select=select, provider=SimpleNamespace(call=call), delivery=lambda _: None)
        selection = CombinedSelection({lane: adapter(lane) for lane in ports}, ports)
        result = await selection.select({"identity": {}, "shared_context": {}, "selection_mode": "combined",
            "prepared_lanes": {lane: {"candidates": candidates} for lane in ports}})
        if submitted or shared:
            assert all(result["prepared_lanes"][lane].get("preparation_error") for lane in ports)
            assert calls == (["combined"] if submitted else [])
        else:
            remaining = "feed" if invalid_lane == "inbox" else "inbox"
            assert result["prepared_lanes"][invalid_lane]["preparation_error"]["status"] == "failed"
            assert result["prepared_lanes"][remaining]["selections"] == [{"target_id": "0"}]
            assert calls == [remaining]
    asyncio.run(scenario())


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
