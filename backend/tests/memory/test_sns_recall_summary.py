import asyncio
import json
from types import SimpleNamespace
from time import monotonic

import pytest

from app.contracts.retrieval_observation import Observation, current
from app.domains.memory.contracts.hybrid_recall import (
    HybridAxesUnavailable, RecallAxisReceipt, RecallAxisStatus,
    HybridEmbeddingUsage, HybridRecallResult,
)
from app.runtime.autonomous_activity.recall import SelectedRecall, context_memories


def service_result(request):
    return HybridRecallResult(request.request_id, request.call_id, request.envelope_hash, request.scope,
        RecallAxisStatus.READY, (), tuple(RecallAxisReceipt(a, RecallAxisStatus.READY, True, 0, 1) for a in ("fts", "vector")),
        (), HybridEmbeddingUsage(), 0, 0, 0)


@pytest.mark.parametrize("error,category", [
    (TimeoutError("private-query"), "deadline"),
    (OSError(5, "private-path"), "io_error"),
    (HybridAxesUnavailable(tuple(RecallAxisReceipt(a, RecallAxisStatus.UNAVAILABLE, True, 0, 10,
        "memory_fts_unavailable" if a == "fts" else "memory_vector_unavailable") for a in ("fts", "vector"))), "axes_unavailable"),
])
def test_failure_summary_is_safe_and_does_not_enable_detailed_capture(error, category):
    async def execute(request, **kwargs):
        assert kwargs["final_reserve_seconds"] == 3
        raise error
    observation = Observation(detailed=False)
    token = current.set(observation)
    try:
        recall = SelectedRecall(SimpleNamespace(execute=execute), owner_id="o", world_id="w", actor_id="a")
        result = asyncio.run(recall.one(activity_id="act", target={"target_id": "t"}, query={"query": "private-query"}))
        assert result["status"] == "unavailable"
        assert result["summary"]["category"] == category
        assert len(json.dumps(result["summary"]).encode()) <= 8192
        assert "private" not in json.dumps(result)
        assert "summary" not in context_memories({"t": result})["t"]
        assert observation.search_trace is None
    finally:
        current.reset(token)


def test_three_targets_share_one_deadline_and_keep_two_in_flight():
    deadlines, active, peak = [], 0, 0
    async def execute(request, *, deadline, final_reserve_seconds):
        nonlocal active, peak
        deadlines.append(deadline)
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(.02)
            return service_result(request)
        finally:
            active -= 1
    recall = SelectedRecall(SimpleNamespace(execute=execute), owner_id="o", world_id="w", actor_id="a")
    targets = [{"target_id": str(i)} for i in range(3)]
    started = monotonic()
    result = asyncio.run(recall.selected(activity_id="act", targets=targets,
        queries=[{"target_id": t["target_id"], "query": "fixture"} for t in targets], deadline=started+1))
    assert peak == 2 and len(set(deadlines)) == 1
    assert deadlines[0] == started+1
    assert all(r["status"] == "empty" for r in result.values())
    assert result["2"]["summary"]["queue_ms"] >= 10
    assert monotonic()-started < 1
