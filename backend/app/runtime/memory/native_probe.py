"""Explicit packaging diagnostic using synthetic data in a new output directory."""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from time import monotonic

from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument, MemoryVectorQuery
from app.runtime.memory.vector_resources import bundled_vector_index
from app.runtime.memory.vector_worker import VectorReadWorkers


async def probe(output: Path):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    index = bundled_vector_index(output / "synthetic.sqlite3")
    info = index.open()
    workers = VectorReadWorkers(database_path=index.database_path, extension_path=index._extension,
        extension_sha256=hashlib.sha256(index._extension.read_bytes()).hexdigest())
    scope = MemoryScope("native-probe-owner", "native-probe-world", "native-probe-subject")
    vector = (1.0,) + (0.0,) * 767
    query = MemoryVectorQuery(scope, "native-probe-768", vector)
    rows = []
    for count in (0, 1, 2):
        if count:
            index.upsert((MemoryVectorDocument(f"probe-{count}", f"probe-{count}", scope, 1,
                "a" * 64, query.profile, vector, datetime.now(UTC)),))
        result = await workers.search(query, deadline=monotonic()+20)
        assert len(result.hits) == count and result.allowed_count == count
        foreign = await workers.search(replace(query, scope=replace(scope, owner_id="foreign")), deadline=monotonic()+20)
        assert not foreign.hits
        assert not workers.active_processes
        rows.append({"count": count, "hits": len(result.hits), "cross_owner_hits": len(foreign.hits), "worker_joined": True})
    receipt = {"status": "passed", "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version, "vec1": info,
        "extension_sha256": hashlib.sha256(index._extension.read_bytes()).hexdigest(),
        "index": "flat", "search": "nn", "dimensions": 768, "ai_calls": 0, "samples": rows}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt), flush=True)


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    asyncio.run(probe(args.output))
    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
