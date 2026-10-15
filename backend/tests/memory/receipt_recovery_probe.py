"""Synthetic, file-backed before/after probe. Run with --repo and --output.

Uses the target checkout's implementation and fixture builders, never app data.
No fixed performance threshold: report SQL, actual writer time and other writers.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import inspect
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path[:0] = [str(args.repo / "backend"), str(args.repo / "backend/tests")]
    from sqlalchemy import create_engine, event, select, func
    from sqlalchemy.orm import Session
    from app.core.sqlite_concurrency import run_sqlite_session_immediate
    from app.runtime.persistence.model_registration import register_models
    from app.runtime.memory.composition import memory_repository
    from app.runtime.memory.situation_sources import SituationSources
    # The probe intentionally loads either the historical or current checkout.
    from importlib.util import find_spec
    if find_spec("app.runtime.memory.situation_application_sources") is not None:
        from app.runtime.memory.situation_application_sources import PreparedSituationSources
    else:
        PreparedSituationSources = SituationSources
    from app.domains.memory.repository.situation_admission import admit
    from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
    from app.domains.memory.repository.situation_apply import prepare_page, apply_page
    from app.domains.memory.models.activity_situation import MemorySituationApplyRun
    from app.domains.memory.models.items import MemoryItem
    from memory.test_p8_l_o_memory_consolidation import _stack
    from memory.test_activity_situation_application import real_source
    from memory.test_activity_situation_contract import NOW, values
    measured = {"sqlite": sqlite3.sqlite_version, "platform": sys.platform, "journal_mode": "wal"}
    page_size = inspect.signature(prepare_page).parameters["page_size"].default
    for source_count, count in ((1, 32), (256, 2)):
        with TemporaryDirectory(prefix="angmoo-receipt-probe-", ignore_cleanup_errors=True) as temp:
            engine = create_engine(f"sqlite:///{Path(temp).as_posix()}/probe.sqlite")
            @event.listens_for(engine, "connect")
            def configure(raw, _):
                raw.execute("PRAGMA foreign_keys=ON")
                raw.execute("PRAGMA journal_mode=WAL")
            register_models().create_all(engine)
            with Session(engine, expire_on_commit=False) as db:
                scope, setting, *_ = _stack(db)
                post = real_source(db, scope)
                for n in range(count):
                    manifest, draft, result = values(db, scope, target=post.id, logical=f"probe-{n}", call=f"call-{n}")
                    source = SituationSources(db).describe(scope, kind="POST", identifier=post.id,
                        delivered=post.body, path="/target/body", role="core", ordinal=0, target=post.id)
                    sources = tuple(replace(source, ordinal=i, payload_path=f"/source/{i}") for i in range(source_count))
                    admit(db, manifest=replace(manifest, sources=sources), draft=draft, result=result, now=NOW)
                get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=NOW)
                request = request_run(db, setting, trigger="manual", request_key="probe-request-001", expected_version=1, now=NOW)
                run_id = request.run_id
                db.commit()
            begun, stop = Event(), Event()
            times, other_times, counts, statements = [], [], [], []
            def statement(_connection, _cursor, sql, *_):
                statements.append(1)
                if sql.upper().startswith("BEGIN IMMEDIATE"):
                    begun.set()
            event.listen(engine, "before_cursor_execute", statement)
            def other_writer():
                assert begun.wait(5)
                while not stop.is_set():
                    start = monotonic()
                    with engine.connect() as connection:
                        connection.exec_driver_sql("BEGIN IMMEDIATE")
                        connection.exec_driver_sql("UPDATE users SET display_name=display_name")
                        connection.commit()
                    other_times.append((monotonic()-start)*1000)
                    sleep(.002)
            started = monotonic()
            with ThreadPoolExecutor(max_workers=1) as pool:
                concurrent = pool.submit(other_writer)
                try:
                    while True:
                        with Session(engine) as db:
                            token = run_sqlite_session_immediate(db, lambda: claim_run(db, run_id, now=NOW))
                        with Session(engine) as db:
                            prepared = prepare_page(db, run_id=run_id, token=token, now=NOW, page_size=page_size)
                        facts = []
                        with Session(engine) as db:
                            applied = run_sqlite_session_immediate(db, lambda: apply_page(db, memory_repository(db),
                                PreparedSituationSources(db), run_id=run_id, token=token, now=NOW, page_size=page_size, prepared=prepared), observer=facts.append)
                            completed = db.get(MemorySituationApplyRun, run_id).state == "completed"
                        times.extend(f["transaction_ms"] for f in facts if f["result"] == "committed")
                        counts.append(applied)
                        if completed:
                            break
                        sleep(.002)  # Fair resubmission, never the idle five-second poll.
                finally:
                    stop.set()
                concurrent.result(5)
            with Session(engine) as db:
                total = db.scalar(select(func.count()).select_from(MemoryItem))
                run = db.get(MemorySituationApplyRun, run_id)
                assert total == count and run.applied_count == count and run.state == "completed"
            measured[str(source_count)] = {"receipts": total, "apply_calls": len(counts),
                "max_receipts_per_commit": max(counts), "sql": len(statements),
                "writer_ms": times, "max_writer_ms": max(times), "other_writer_commits": len(other_times),
                "max_other_writer_wait_ms": max(other_times), "total_ms": round((monotonic()-started)*1000, 3)}
            engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(measured, indent=2), encoding="utf-8")
    print(json.dumps(measured))


if __name__ == "__main__":
    main()
