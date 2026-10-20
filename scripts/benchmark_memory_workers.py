"""Isolated same-budget comparison; synthetic indexes and embeddings, no AI.

Run with the project's Python and optional `uv run --with psutil`. Select an
archived backend using --backend to measure the same harness against old code.
All application imports stay below main so spawn does not reload this harness.
"""
import argparse
import asyncio
from contextlib import closing
import json
from pathlib import Path
import platform
import statistics
import sys
from time import monotonic


async def benchmark(args):
    import hashlib
    import inspect
    import sqlite3
    import psutil
    from datetime import UTC, datetime
    from app.contracts.retrieval_observation import Observation, current
    from app.domains.memory.contracts.recall import (
        MemoryRecallDocument, RecallDocumentKind, CanonicalRecallRecord,
    )
    from app.domains.memory.contracts.scope import MemoryScope
    from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest, HybridHydrationResult
    from app.domains.memory.contracts.vector_projection import MemoryVectorDocument
    from app.domains.memory.service.hybrid_recall import HybridRecallService
    from app.providers.contracts import MeasuredEmbeddingResponse, ProviderUsage
    from app.runtime.memory.fts_worker import FtsReadWorkers
    from app.runtime.memory.vector_worker import VectorReadWorkers
    from app.runtime.memory.hybrid_axes import FtsHybridAxis, VectorHybridAxis
    from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
    from app.runtime.memory.sqlite_vec1 import SqliteMemoryVectorIndex
    from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath

    args.output.mkdir(parents=True, exist_ok=False)
    # Written before measuring. These are this harness's limits, not production
    # memory limits or a promise about other hardware.
    result = {"version": 1, "platform": platform.platform(), "architecture": platform.machine(),
        "cpu_count": psutil.cpu_count(), "physical_ram_bytes": psutil.virtual_memory().total,
        "limits": {"axis_workers": 2, "search_workers_total": 4, "idle_worker_rss_bytes": 512*1024**2,
            "warm_rss_growth_bytes": 64*1024**2, "idle_handles_growth": 16,
            "writer_errors": 0, "idle_checkpoint_busy": 0},
        "embedding": "fixed synthetic vector with 10 ms await; no provider",
        "canonical": "synthetic readonly SQL scope/version revalidation; not production hydration",
        "samples": [], "resources": [], "writer": [], "lag_ms": []}
    receipt = args.output / "performance.json"
    def save():
        receipt.write_text(json.dumps(result, indent=2), encoding="utf-8")
    save()
    scope = MemoryScope("synthetic-owner", "synthetic-world", "synthetic-actor")
    vector = [1.0] + [0.0]*767
    profile = "gemini-embedding-2.768.cos.v1"
    now = datetime(2026, 10, 20, tzinfo=UTC)
    canonical_path = args.output / "canonical.sqlite3"
    with closing(sqlite3.connect(canonical_path)) as db, db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE items(id TEXT PRIMARY KEY,owner TEXT,world TEXT,actor TEXT,version INTEGER)")
        db.execute("CREATE TABLE writes(value INTEGER)")
        db.executemany("INSERT INTO items VALUES(?,?,?,?,1)", [(f"memory-{i}", *(
            scope.owner_id, scope.world_id, scope.subject_world_character_id)) for i in range(args.documents)])
    fts = SqliteMemoryRecallIndex(StaticRuntimeDataPath(args.output / "fts"))
    docs = tuple(MemoryRecallDocument(f"memory-{i}", f"memory-{i}", scope.owner_id,
        scope.world_id, scope.subject_world_character_id, RecallDocumentKind.MEMORY_ITEM,
        f"memory-{i}", "remember the blue garden bench", occurred_at=now,
        metadata={"item_version": "1"}) for i in range(args.documents))
    fts.rebuild(docs)
    digest = hashlib.sha256(args.extension.read_bytes()).hexdigest()
    vec = SqliteMemoryVectorIndex(args.output / "vector.sqlite3",
        extension_path=args.extension, extension_sha256=digest)
    vec.open()
    vec.upsert(tuple(MemoryVectorDocument(doc.document_id, doc.memory_item_id, scope, 1,
        hashlib.sha256(doc.text.encode()).hexdigest(), profile, vector, now) for doc in docs))

    class Canonical:
        def revalidate(self, request, candidates):
            records = []
            with closing(sqlite3.connect(canonical_path.as_uri()+"?mode=ro", uri=True)) as db:
                for item in candidates:
                    row = db.execute("SELECT id FROM items WHERE id=? AND owner=? AND world=? AND actor=? AND version=?",
                        (item.candidate.memory_item_id, request.scope.owner_id, request.scope.world_id,
                         request.scope.subject_world_character_id, item.version)).fetchone()
                    if row:
                        records.append(CanonicalRecallRecord(row[0], RecallDocumentKind.MEMORY_ITEM,
                            row[0], "synthetic memory", now, memory_item_id=row[0]))
            return tuple(records)
        def hydrate(self, request, records):
            return HybridHydrationResult(records, ())
    class Embedder:
        async def query(self, request, *, deadline):
            await asyncio.sleep(.01)
            return MeasuredEmbeddingResponse(tuple(vector), ProviderUsage(), 1)

    control = None
    if "control" in inspect.signature(FtsReadWorkers).parameters:
        from app.runtime.memory.search_worker_pool import SearchWorkerControl
        control = SearchWorkerControl()
    options = {"control": control} if control else {}
    fw = FtsReadWorkers(database_path=fts.database_path, **options)
    vw = VectorReadWorkers(database_path=vec.database_path, extension_path=args.extension,
        extension_sha256=digest, **options)
    service = HybridRecallService(fts=FtsHybridAxis(fw, lexical_policy="group_or_v1"),
        vector=VectorHybridAxis(vw, Embedder()), canonical=Canonical())
    parent = psutil.Process()
    running = True
    observed = set()
    cpu = {}
    def snapshot():
        workers = parent.children(recursive=True)
        info = []
        for p in workers:
            try:
                if not p.is_running() or "resource_tracker" in " ".join(p.cmdline()):
                    continue
                observed.add(p.pid)
                times = p.cpu_times()
                cpu[p.pid] = times.user + times.system
                info.append({"pid": p.pid, "rss": p.memory_info().rss,
                    "handles": p.num_handles() if sys.platform == "win32" else p.num_fds(),
                    "threads": p.num_threads()})
            except psutil.Error:
                pass
        return {"workers": info, "parent_rss": parent.memory_info().rss,
            "parent_threads": parent.num_threads()}
    async def monitor():
        while running:
            start = monotonic()
            await asyncio.sleep(.02)
            result["lag_ms"].append(max(0, monotonic()-start-.02)*1000)
            result["resources"].append(snapshot())
    monitor_task = asyncio.create_task(monitor())
    sequence = 0
    async def query(budget, label, deadline=None):
        nonlocal sequence
        sequence += 1
        observation = Observation(request_id="synthetic", detailed=True)
        token = current.set(observation)
        started = monotonic()
        row = {"budget": budget, "case": label}
        try:
            request = HybridRecallRequest("synthetic", str(sequence), "a"*64, scope,
                "blue garden bench", profile, (RecallDocumentKind.MEMORY_ITEM,))
            options = {}
            if budget in (15, 30) and "final_reserve_seconds" in inspect.signature(service.execute).parameters:
                options["final_reserve_seconds"] = 3
            value = await service.execute(request, deadline=deadline or started+budget, **options)
            row.update(status=value.status.value, count=len(value.records))
            assert len(value.records) == min(args.documents, request.result_limit)
            assert all(r.memory_item_id.startswith("memory-") for r in value.records)
        except (RuntimeError, TimeoutError) as exc:
            row.update(status="unavailable", error=type(exc).__name__)
        finally:
            row["elapsed_ms"] = (monotonic()-started)*1000
            if observation.search_trace:
                trace = observation.search_trace.payload()
                row["stages"] = trace["stages"]
                row["terminals"] = trace["terminals"]
            current.reset(token)
            result["samples"].append(row)
        return row
    def write_probe(phase="idle"):
        # Independent writers touch only synthetic databases, including the FTS
        # file that the search processes just read.
        for path in (canonical_path, fts.database_path):
            with closing(sqlite3.connect(path, timeout=2)) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS bench_write(value INTEGER)")
                start = monotonic()
                db.execute("BEGIN IMMEDIATE")
                acquired = monotonic()
                db.execute("INSERT INTO bench_write VALUES(1)")
                db.commit()
                ended = monotonic()
                checkpoint = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            result["writer"].append({"database": path.name, "phase": phase, "wait_ms": (acquired-start)*1000,
                "hold_ms": (ended-acquired)*1000, "checkpoint": list(checkpoint)})
    try:
        # Cold is deliberately measured, not hidden behind setup.
        await query(20, "cold")
        for budget in (10, 20, 15, 30):
            for _ in range(args.samples):
                await query(budget, "warm")
            write_probe()
            save()
            print(json.dumps({"completed_budget": budget, "samples": args.samples}), flush=True)
        result["idle_before"] = snapshot()
        for _ in range(args.leak_samples):
            await query(20, "reuse-leak")
        result["idle_after"] = snapshot()
        for budget in (15, 30):
            semaphore = asyncio.Semaphore(2)
            deadline = monotonic() + budget
            async def queued():
                queued_at = monotonic()
                async with semaphore:
                    row = await query(budget, "three-targets", deadline)
                    row["queue_ms"] = (monotonic()-queued_at)*1000-row["elapsed_ms"]
            await asyncio.gather(*(queued() for _ in range(3)))
        await asyncio.gather(query(20, "mixed-chat"), query(30, "mixed-sns"),
            query(30, "mixed-sns"))
        # An independent writer runs while both axes receive search work.
        # The trace proves overlap at the request level, not an intentionally
        # extended native SQL transaction. Idle probes separately check that
        # completed searches retain no WAL read transaction.
        await asyncio.gather(query(20, "overlapping-writer"),
            asyncio.to_thread(write_probe, "search-request-overlap"))
        if control:
            # Fail one idle synthetic worker; the next request must retire the
            # dead peer before a later demand can replace that capacity.
            slot = fw._workers[0]
            slot.process.terminate()
            await control.run(slot.process.join, 1)
            await query(20, "worker-failure")
            await query(20, "replacement")
        write_probe()
    finally:
        # The archived one-shot implementation reaps on every call and has no
        # persistent-pool stop API. Both implementations must have zero live
        # search processes at this boundary.
        if hasattr(fw, "stop"):
            await fw.stop()
        if hasattr(vw, "stop"):
            await vw.stop()
        running = False
        await monitor_task
        if control:
            control.close()
        assert not fw.active_processes and not vw.active_processes
        result["spawned_pids"] = sorted(observed)
        result["observed_worker_cpu_seconds"] = sum(cpu.values())
        result["parent_cpu_seconds"] = sum(parent.cpu_times()[:2])
        result["summaries"] = []
        for budget in (10, 20, 15, 30):
            values = [s["elapsed_ms"] for s in result["samples"] if s["case"] == "warm" and s["budget"] == budget]
            if values:
                result["summaries"].append({"budget": budget, "n": len(values),
                    "p50_ms": statistics.median(values), "p95_ms": sorted(values)[int((len(values)-1)*.95)],
                    "max_ms": max(values)})
        save()
    print(json.dumps({"path": str(receipt), "summaries": result["summaries"],
        "failures": sum(s["status"] == "unavailable" for s in result["samples"])}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--documents", type=int, default=34)
    parser.add_argument("--leak-samples", type=int, default=100)
    args = parser.parse_args()
    args.backend = args.backend.resolve()
    args.extension = args.extension.resolve()
    args.output = args.output.resolve()
    sys.path.insert(0, str(args.backend))
    asyncio.run(benchmark(args))


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
