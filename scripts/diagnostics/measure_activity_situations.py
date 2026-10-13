"""Isolated T17 synthetic load. No app server, real credentials or provider calls.

Seed existing situations in bulk, then measure 1,000 real canonical applications
at 10k/100k population. This measures backlog under load, not AI output quality.
"""
from pathlib import Path
import argparse
import json
import sys
from time import perf_counter
from dataclasses import replace
from hashlib import sha256
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests")]
from sqlalchemy import create_engine, event, insert, select, text
from sqlalchemy.orm import Session, sessionmaker
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_contract import NOW, values
from memory.test_activity_situation_application import real_source, receipt, apply
from memory.test_activity_situation_recall import readers
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.memory.composition import memory_repository
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.activity_situation import MemorySituationReceipt, MemoryActivitySituationInfo, MemoryActivitySituationSource
from app.domains.memory.models.embedding import MemoryVectorEligibility
from app.domains.memory.repository.situation_runs import request_run, claim_run
from app.domains.memory.repository.situation_apply import apply_page
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.contracts.recall import MemoryRecallDocument, MemoryRecallSearchQuery, RecallDocumentKind


def row_values(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def measure(directory, population):
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "canonical.sqlite3"
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"timeout": 30})
    @event.listens_for(engine, "connect")
    def pragmas(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
    register_models().create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        scope, setting, _, memory, *_ = _stack(db)
        post = real_source(db, scope)
        first = receipt(db, scope, post)
        apply(db, setting, memory)
        item = db.get(MemoryItem, first.applied_item_id)
        base = {model: row_values(db.get(model, item.id)) for model in (MemoryItem, MemoryActivitySituationInfo, MemoryVectorEligibility)}
        origin = row_values(db.scalar(select(MemoryActivitySituationSource)))
        admission = row_values(first)
        started = perf_counter()
        for start in range(1, population, 1000):
            items, receipts, infos, sources, vectors = [], [], [], [], []
            for number in range(start, min(population, start + 1000)):
                identifier = f"perf-{number:06d}"
                pending = number >= population - 1000
                r = {**admission, "sequence": number + 1, "logical_activity_id": identifier,
                    "run_id": None, "state": "pending" if pending else "applied",
                    "applied_item_id": None if pending else identifier, "applied_at": None if pending else NOW}
                receipts.append(r)
                if not pending:
                    items.append({**base[MemoryItem], "id": identifier})
                    infos.append({**base[MemoryActivitySituationInfo], "memory_item_id": identifier, "receipt_sequence": number+1})
                    sources.append({**origin, "memory_item_id": identifier, "evidence_id": None})
                    vectors.append({**base[MemoryVectorEligibility], "memory_item_id": identifier})
            if items:
                db.execute(insert(MemoryItem.__table__), items)
            db.execute(insert(MemorySituationReceipt.__table__), receipts)
            if infos:
                db.execute(insert(MemoryActivitySituationInfo.__table__), infos)
                db.execute(insert(MemoryActivitySituationSource.__table__), sources)
                db.execute(insert(MemoryVectorEligibility.__table__), vectors)
            db.commit()
        seeded_seconds = perf_counter() - started
        request = request_run(db, memory.get_scope_setting(scope), trigger="manual", request_key="load-apply-1000",
            expected_version=1, now=NOW)
        db.commit()
        pages, foreground, total = [], [], 0
        for _ in range(10):
            started = perf_counter()
            token = claim_run(db, request.run_id, now=NOW)
            db.commit()
            total += apply_page(db, memory, SituationSources(db), run_id=request.run_id, token=token, now=NOW)
            db.commit()
            pages.append(perf_counter() - started)
            # A separate foreground transaction is allowed between bounded pages.
            started = perf_counter()
            with engine.begin() as connection:
                connection.execute(text("UPDATE memory_scope_settings SET id=id WHERE id=:id"), {"id": setting.id})
            foreground.append(perf_counter() - started)
        assert total == 1000
        assert db.scalar(select(MemorySituationReceipt.sequence).where(MemorySituationReceipt.state == "pending")) is None
        admission_times = []
        for n in range(20):
            manifest, draft, result = values(db, scope, logical=f"chat-like-{n}", call=f"extra-{n}")
            started = perf_counter()
            admit(db, manifest=manifest, draft=draft, result=replace(result, lane="chat"), now=NOW)
            db.commit()
            admission_times.append(perf_counter()-started)
        index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(directory / "fts"))
        def documents():
            for row in db.scalars(select(MemoryItem).execution_options(yield_per=1000)):
                yield MemoryRecallDocument(f"memory-item:{row.id}", row.id, scope.owner_id, scope.world_id,
                    scope.subject_world_character_id, RecallDocumentKind.MEMORY_ITEM, row.id, row.summary,
                    occurred_at=NOW, metadata={"item_version": str(row.version)})
        started = perf_counter(); index.rebuild(documents()); fts_seconds = perf_counter()-started
        started = perf_counter()
        hits = index.search(MemoryRecallSearchQuery(scope, "평범한 하루", (RecallDocumentKind.MEMORY_ITEM,), 12))
        search_ms = (perf_counter()-started)*1000
        reader, query, ranked, _ = readers(db, scope, item)
        started = perf_counter(); selected = reader.revalidate(query, (ranked,)); hydrated = reader.hydrate(query, selected)
        hydration_ms = (perf_counter()-started)*1000
        assert hits and hydrated.records
        db.rollback()
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        result = {"population": population, "seed_seconds": seeded_seconds, "applied": total,
            "apply_seconds": sum(pages), "apply_per_second": total/sum(pages), "page_max_ms": max(pages)*1000,
            "foreground_write_max_ms": max(foreground)*1000, "additional_admission_mean_ms": sum(admission_times)/len(admission_times)*1000,
            "canonical_bytes": path.stat().st_size, "fts_build_seconds": fts_seconds,
            "fts_bytes": index.database_path.stat().st_size, "fts_search_ms": search_ms, "selected_hydration_ms": hydration_ms,
            "pending_after_application": 0, "later_receipts_kept_pending": 20,
            "real_ai_calls": 0, "embedding_api_latency": "not measured; no API",
            "raw_768_float32_vector_bytes_estimate": population*768*4, "vector_index": "requires verified Vec1 extension; separate native suite"}
        index.close()
    engine.dispose()
    return result


def measure_vectors(directory, population, resources):
    """Measure the packaged native index with deterministic, synthetic vectors."""
    from app.domains.memory.contracts.scope import MemoryScope
    from app.domains.memory.contracts.vector_projection import MemoryVectorDocument, MemoryVectorQuery
    from app.runtime.memory.sqlite_vec1 import SqliteMemoryVectorIndex, VectorCancellation
    from time import monotonic
    import sqlite3
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "vectors.sqlite3"
    manifest = json.loads((resources / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.7"
    assert manifest["source_sha256"] == "8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86"
    index = SqliteMemoryVectorIndex(path, extension_path=resources / manifest["filename"], extension_sha256=manifest["sha256"])
    index.open()
    scope = MemoryScope("synthetic-owner", "synthetic-world", "synthetic-subject")
    pool = [tuple(1.0 if dim == i else 0.01 for dim in range(768)) for i in range(256)]
    times = []
    for start in range(0, population, 1000):
        documents = tuple(MemoryVectorDocument(f"item:{n}", str(n), scope, 1, sha256(str(n).encode()).hexdigest(),
            "synthetic-768", pool[n % len(pool)], NOW) for n in range(start, min(start+1000, population)))
        started = perf_counter()
        index.upsert(documents)
        times.append(perf_counter()-started)
    searches = []
    for vector in pool[:10]:
        started = perf_counter()
        result = index.search(MemoryVectorQuery(scope, "synthetic-768", vector, limit=12),
            cancellation=VectorCancellation(monotonic()+10))
        searches.append((perf_counter()-started)*1000)
        assert len(result.hits) == 12 and result.allowed_count == population
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return {"population": population, "dimensions": 768, "vector_source": "deterministic synthetic values, not model embeddings",
        "index": "packaged Vec1 0.7 flat cosine", "index_bytes": path.stat().st_size,
        "upsert_seconds": sum(times), "upsert_per_second": population/sum(times),
        "batch_1000_max_ms": max(times)*1000, "query_mean_ms": sum(searches)/len(searches),
        "query_max_ms": max(searches), "real_ai_calls": 0, "semantic_quality": "not measured"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, help="Optional empty synthetic-data root, separate from exported measurements")
    parser.add_argument("--vector-only", action="store_true", help="Require the verified packaged Vec1 extension; use synthetic vectors only")
    parser.add_argument("--vector-resources", type=Path, help="Directory containing the packaged Vec1 binary and manifest")
    args = parser.parse_args()
    if args.vector_only and args.vector_resources is None:
        parser.error("--vector-only requires --vector-resources")
    args.output.mkdir(parents=True, exist_ok=True)
    data_root = args.data_root or args.output
    results = []
    for population in (10_000, 100_000):
        result = (measure_vectors(data_root / str(population), population, args.vector_resources) if args.vector_only
            else measure(data_root / str(population), population))
        results.append(result)
        (args.output / "measurements.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
