"""Overflow and interleaved detailed capture remain bounded and request-local."""
import asyncio
import json
import os
from statistics import quantiles
from time import perf_counter

import pytest

from app.contracts.retrieval_observation import Observation, current, detail, observe


def test_byte_limit_preserves_final_evidence_summary():
    observation = Observation()
    token = current.set(observation)
    try:
        for index in range(48):
            observe("search", step=index, operation="a" * 80, method="b" * 80,
                    reason="c" * 80, source="d" * 80, phase="e" * 80)
        observe("crg_input", items=3)
        observe("crg_completed", output_tokens=120)
    finally:
        current.reset(token)
    payload = observation.payload()
    assert len(json.dumps(payload, ensure_ascii=True).encode()) <= 16384
    assert payload["omitted_events"] > 1
    assert payload["events"][-2:] == [
        {"event": "crg_input", "items": 3},
        {"event": "crg_completed", "output_tokens": 120},
    ]


async def detailed_request(marker):
    observation = Observation(request_id=marker, detailed=True)
    token = current.set(observation)
    try:
        for index in range(32):
            observe("search", step=index, returned=1)
            detail(search_text=marker * 750, normalized_query=marker * 750)
            await asyncio.sleep(0)
        observe("crg_input", items=2)
        payload = observation.payload()
        assert marker not in json.dumps(payload)
        assert len(json.dumps(observation.details, ensure_ascii=True).encode()) <= 65536
        assert all(row["search_text"].startswith(marker) for row in observation.details)
        assert 0 < len(observation.details) <= 24
        return payload, observation.details
    finally:
        current.reset(token)


async def interleaved_pair():
    result = await asyncio.gather(detailed_request("synthetic-alpha"), detailed_request("synthetic-beta"))
    assert current.get() is None
    return result


def test_two_interleaved_detailed_requests_do_not_mix():
    first, second = asyncio.run(interleaved_pair())
    assert first[1] != second[1]
    assert current.get() is None


@pytest.mark.skipif(os.environ.get("ANGMOO_DIAGNOSTIC_BENCHMARK") != "1", reason="explicit performance run")
def test_maximum_detail_collection_two_concurrent_requests_100_samples():
    samples = []
    for index in range(105):
        started = perf_counter()
        asyncio.run(interleaved_pair())
        if index >= 5:
            samples.append((perf_counter() - started) * 1000)
    print(f"diagnostic_max_detail_pair_samples=100 p95_ms={quantiles(samples, n=20)[18]:.3f}")
