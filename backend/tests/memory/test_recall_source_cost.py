"""Non-profiled repeatable cost evidence, separate from deterministic correctness."""
from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter

from sqlalchemy import event
from memory.recall_cost_fixture import build_cost_case, NOW


def test_sns_source_cost(tmp_path):
    engine, reader, request, candidates = build_cost_case(tmp_path / "canonical.sqlite")
    counts = []
    def sql(*_):
        counts.append(1)
    event.listen(engine, "before_cursor_execute", sql)
    measured = {}
    try:
        for name, query in (("50", request), ("date_excluded", replace(request, occurred_from=NOW+timedelta(days=1)))):
            reader.revalidate(query, candidates)
            samples, queries = [], []
            for _ in range(int(os.environ.get("ANGMOO_COST_REPEATS", "3"))):
                counts.clear()
                start = perf_counter()
                records = reader.revalidate(query, candidates)
                samples.append((perf_counter()-start)*1000)
                queries.append(len(counts))
                assert len(records) == (50 if name == "50" else 0)
            measured[name] = {"sql": median(queries), "median_ms": median(samples),
                "p95_ms": sorted(samples)[min(len(samples)-1, int(len(samples)*.95))],
                "max_ms": max(samples), "samples": len(samples)}
    finally:
        event.remove(engine, "before_cursor_execute", sql)
        engine.dispose()
    print("SNS_SOURCE_COST " + json.dumps(measured, sort_keys=True))
    if output := os.environ.get("ANGMOO_COST_OUTPUT"):
        Path(output).write_text(json.dumps(measured, indent=2), encoding="utf-8")
