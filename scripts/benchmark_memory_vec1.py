"""Reproducible native flat NN scale probe; synthetic data and zero AI calls."""
from __future__ import annotations
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import sys
from time import monotonic, process_time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument, MemoryVectorQuery
from app.runtime.memory.sqlite_vec1 import SqliteMemoryVectorIndex, VectorCancellation
from app.runtime.memory.vector_worker import VectorReadWorkers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    database = args.output / "scale.sqlite3"
    if database.exists():
        raise RuntimeError("benchmark_output_exists_choose_new_directory")
    digest = hashlib.sha256(args.extension.read_bytes()).hexdigest()
    index = SqliteMemoryVectorIndex(database, extension_path=args.extension, extension_sha256=digest)
    info = index.open()
    scope = MemoryScope("benchmark-owner", "benchmark-world", "benchmark-subject")
    rng = random.Random(20260914)
    vectors = [tuple(rng.uniform(-1, 1) for _ in range(768)) for _ in range(256)]
    query = MemoryVectorQuery(scope, "benchmark-768-cos", vectors[0])
    now = datetime.now(UTC)
    workers = VectorReadWorkers(database_path=database, extension_path=args.extension, extension_sha256=digest)
    def document(i):
        return MemoryVectorDocument(f"doc-{i:06}", f"item-{i:06}", scope, 1, "a"*64,
            query.profile, vectors[i % len(vectors)], now)
    previous = 0
    receipt = {"platform": platform.platform(), "vec1": info, "extension_sha256": digest,
               "dimensions": 768, "search": "nn", "index": "flat", "distance": "cos", "ai_calls": 0, "samples": []}
    for count in (0, 1, 2, 1000, 10000, 100000):
        start, cpu = monotonic(), process_time()
        for offset in range(previous, count, 1000):
            index.upsert(tuple(document(i) for i in range(offset, min(count, offset + 1000))))
        build_seconds, build_cpu = monotonic() - start, process_time() - cpu
        durations = []
        for _ in range(10):
            start = monotonic()
            result = index.search(query, cancellation=VectorCancellation(monotonic() + 30))
            durations.append((monotonic() - start)*1000)
            assert result.allowed_count == count and len(result.hits) == min(count, 50)
            assert all(hit.document_id.startswith("doc-") for hit in result.hits)
        async def lifecycle():
            start = monotonic()
            values = await asyncio.gather(*(workers.search(query, deadline=monotonic()+30) for _ in range(2)))
            parallel_ms = (monotonic()-start)*1000
            assert all(len(value.hits) == min(count, 50) for value in values)
            task = asyncio.create_task(workers.search(query, deadline=monotonic()+30))
            while not workers.active_processes:
                await asyncio.sleep(0)
            cancel_start = monotonic()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert not workers.active_processes
            return parallel_ms, (monotonic()-cancel_start)*1000
        parallel_ms, cancel_ms = asyncio.run(lifecycle())
        foreign = index.search(replace(query, scope=replace(scope, owner_id="other")), cancellation=VectorCancellation(monotonic()+30))
        assert foreign.hits == () and foreign.allowed_count == 0
        row = {"count": count, "build_seconds": build_seconds, "build_cpu_seconds": build_cpu,
            "direct_ms": durations, "direct_p50_ms": statistics.median(durations),
            "direct_p95_ms": sorted(durations)[-1], "two_worker_wall_ms": parallel_ms,
            "cancel_join_ms": cancel_ms, "cross_scope_hits": 0,
            "database_bytes": database.stat().st_size,
            "wal_bytes": Path(str(database)+"-wal").stat().st_size if Path(str(database)+"-wal").exists() else 0}
        try:
            import psutil
            row["process_rss_bytes"] = psutil.Process().memory_info().rss
        except ImportError:
            row["process_rss_bytes"] = None
        receipt["samples"].append(row)
        (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(row), flush=True)
        previous = count


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
