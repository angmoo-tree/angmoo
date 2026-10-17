"""Manual, repeatable benchmark; fake axes and temporary WAL data only.

Run with the pinned Python environment. ANGMOO_COST_OUTPUT selects the JSON file.
An extracted baseline app can run the same harness without changing a checkout.
"""
import asyncio
from dataclasses import asdict, replace
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import monotonic, perf_counter
from unittest.mock import patch
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from app.contracts.retrieval_observation import Observation, current
from app.contracts.search_diagnostics import trace_payload
from app.domains.memory.contracts.hybrid_recall import HybridAxisResult, RecallAxisReceipt, RecallAxisStatus
from app.domains.memory.service.hybrid_recall import HybridRecallService
from app.runtime.memory.canonical_worker import CanonicalReadWorker, DeadlineSessionFactory
from app.runtime.autonomous_activity.revalidation import assert_memories_current
from memory.recall_cost_fixture import build_cost_case, NOW


def semantic(value):
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items() if k not in {"ref", "reference", "follows", "thought_ref"}}
    if isinstance(value, list):
        return [semantic(v) for v in value]
    return value


class Clock(datetime):
    @classmethod
    def now(cls, _tz=None): return NOW


async def measure(root, stride):
    engine, reader, request, candidates = build_cost_case(root / f"cost-{stride}.sqlite", stride=stride)
    request = replace(request, result_limit=12)
    sessions = DeadlineSessionFactory(sessionmaker(engine))
    reader.factory, reader.access_observer = sessions, sessions.record_access
    if hasattr(reader, "phase"):
        reader.phase = sessions.phase
    worker = CanonicalReadWorker(sessions, reader)
    simulated_delay = 0
    class Axis:
        def __init__(self, name): self.name = name
        async def search(self, *_args, **_kwargs):
            if self.name == "vector" and simulated_delay:
                await asyncio.sleep(simulated_delay)
            return HybridAxisResult(candidates, RecallAxisReceipt(self.name, RecallAxisStatus.READY, True, len(candidates), 0))
    service = HybridRecallService(fts=Axis("fts"), vector=Axis("vector"), canonical=worker)
    counts = []
    def count(*_): counts.append(1)
    event.listen(engine, "before_cursor_execute", count)
    repeats = int(os.environ.get("ANGMOO_COST_REPEATS", "20"))
    output = {}
    async def run(): return await service.execute(request, deadline=monotonic()+4)
    try:
        result = await run()
        samples, queries = [], []
        expected = sha256(json.dumps(semantic([json.loads(row.text) for row in result.records]), sort_keys=True).encode()).hexdigest()
        for _ in range(repeats):
            counts.clear()
            started = perf_counter()
            result = await run()
            samples.append((perf_counter()-started)*1000)
            queries.append(len(counts))
            assert expected == sha256(json.dumps(semantic([json.loads(row.text) for row in result.records]), sort_keys=True).encode()).hexdigest()
            assert result.fused_count == 50 and result.excluded_count == 0
        output["hybrid_fake_axes"] = {"median_ms": median(samples), "p95_ms": sorted(samples)[min(len(samples)-1, int(len(samples)*.95))],
            "max_ms": max(samples), "failures": 0, "sql": median(queries), "samples": repeats,
            "semantic_sha256": expected, "returned": len(result.records)}
        observation = Observation(request_id="cost", detailed=True)
        token = current.set(observation)
        try:
            await run()
            output["diagnostic_sample"] = trace_payload()["canonical_reads"]
        finally:
            current.reset(token)
        memory = {"ranked_memory_ids": [row.memory_item_id for row in result.records],
                  "packets": [json.loads(row.text) for row in result.records]}
        snapshot = json.loads(json.dumps(asdict(result.validation_snapshot), default=str))
        samples, queries = [], []
        with patch("app.runtime.autonomous_activity.revalidation.datetime", Clock):
            for _ in range(repeats):
                counts.clear()
                started = perf_counter()
                with sessionmaker(engine)() as db:
                    assert_memories_current(db, owner_id=request.scope.owner_id, world_id=request.scope.world_id,
                        actor_id=request.scope.subject_world_character_id, memories={"target": memory}, validations={"target": snapshot})
                samples.append((perf_counter()-started)*1000)
                queries.append(len(counts))
        output["fresh_guard"] = {"median_ms": median(samples), "p95_ms": sorted(samples)[min(len(samples)-1, int(len(samples)*.95))],
            "max_ms": max(samples), "failures": 0, "sql": median(queries), "samples": repeats}
        if hasattr(service, "assert_current"):
            samples, queries = [], []
            for _ in range(repeats):
                counts.clear()
                started = perf_counter()
                await service.assert_current(result, tuple(row.memory_item_id for row in result.records), deadline=monotonic()+4)
                samples.append((perf_counter()-started)*1000)
                queries.append(len(counts))
            output["fresh_chat_guard"] = {"median_ms": median(samples), "max_ms": max(samples),
                "sql": median(queries), "samples": repeats, "failures": 0}
        if os.environ.get("ANGMOO_COST_SIMULATED_LATENCY") == "1":
            simulated_delay = .65
            samples = []
            for _ in range(repeats):
                started = perf_counter()
                await run()  # Existing 4 second deadline; no real embedding or network.
                samples.append((perf_counter()-started)*1000)
            output["fake_embedding_650ms"] = {"median_ms": median(samples), "max_ms": max(samples), "samples": repeats, "failures": 0}
        return output
    finally:
        await worker.stop()
        event.remove(engine, "before_cursor_execute", count)
        engine.dispose()


async def main():
    with TemporaryDirectory(prefix="angmoo-recall-cost-") as directory:
        results = {name: await measure(Path(directory), stride) for name, stride in (("shared", 5), ("unique", 10))}
    Path(os.environ["ANGMOO_COST_OUTPUT"]).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
