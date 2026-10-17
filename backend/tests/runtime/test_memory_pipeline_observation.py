"""Opt-in bounded evidence must never wait for disk on a business thread."""
from datetime import UTC, datetime, timedelta
import json
from threading import Event, Thread
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine
from app.core import work_observation as observation
from app.core.sqlite_concurrency import run_sqlite_immediate
from app.runtime.diagnostics.memory_pipeline_observation import MemoryPipelineObserver
from app.runtime.diagnostics.memory_pipeline_report import capability, read_events


def manifest(session="a"):
    now = datetime.now(UTC)
    return {"session_id":"sns-"+session*32, "world_id":"w", "actor_ids":["a"],
        "started_at":now.isoformat(), "tail_ends_at":(now+timedelta(minutes=5)).isoformat(),
        "database_relative_path":"canonical.sqlite3"}


def directory(root, value):
    return root / "diagnostics/sns" / value["session_id"]


def test_disabled_scope_and_bounded_loss_do_not_serialize_on_submit(tmp_path, monkeypatch):
    observer = MemoryPipelineObserver(tmp_path, "process", capacity=1)
    assert not observation.enabled() and not list(tmp_path.iterdir())
    value=manifest(); observer.attach(value)
    original=json.dumps
    try:
        monkeypatch.setattr(json, "dumps", lambda *a, **k: pytest.fail("serialization on business thread"))
        with observation.scope(world_id="w", actor_id="a"):
            observation.emit("result", item_id="one", boundary="current", body="PRIVATE-SENTINEL", api_key="PRIVATE-SENTINEL", credential_id="PRIVATE-ID")
            observation.emit("result", item_id="two", boundary="current")
        with observation.scope(world_id="other", actor_id="a"):
            observation.emit("result", item_id="foreign")
        monkeypatch.setattr(json,"dumps",original)
    finally:
        observer.close()
    events,damaged=read_events(directory(tmp_path,value))
    health=capability(directory(tmp_path,value))["processes"][0]
    assert len(events)==1 and not damaged
    assert sum(health["expected"].values())==2 and health["dropped"]==1
    assert health["final"] and health["queued"]==0
    assert events[0]["credential_alias"]=="key-1"
    assert "PRIVATE" not in json.dumps(events) and "foreign" not in json.dumps(events)
    assert not observation.enabled()


def test_blocked_file_flush_does_not_hold_writer_or_admission_lock(tmp_path, monkeypatch):
    from app.runtime.diagnostics import memory_pipeline_observation as recorder
    observer=MemoryPipelineObserver(tmp_path,"process"); value=manifest();observer.attach(value)
    entered,release=Event(),Event()
    original=recorder.atomic_json
    def blocked(*args,**kwargs):
        entered.set(); assert release.wait(5); return original(*args,**kwargs)
    monkeypatch.setattr(recorder,"atomic_json",blocked)
    observer.last_flush=0
    thread=Thread(target=observer.flush);thread.start();assert entered.wait(5)
    engine=create_engine(f"sqlite:///{tmp_path/'canonical.sqlite3'}")
    try:
        with ThreadPoolExecutor() as pool:
            result=pool.submit(run_sqlite_immediate,engine,lambda db: db.exec_driver_sql("CREATE TABLE evidence(id INTEGER)"))
            result.result(timeout=2)
    finally:
        release.set();thread.join(5);observer.close();engine.dispose()
    assert not thread.is_alive()
    events,_=read_events(directory(tmp_path,value))
    assert any(e.get("boundary")=="committed" for e in events)


def test_rebound_context_cannot_attribute_old_work_to_new_session(tmp_path):
    observer=MemoryPipelineObserver(tmp_path,"process"); first=manifest();second=manifest("b")
    observer.attach(first)
    try:
        with observation.scope(world_id="w",actor_id="a",item_id="old"):
            observer.attach(second)
            observation.emit("result",boundary="committed")
        with observation.scope(world_id="w",actor_id="a",item_id="new"):
            observation.emit("result",boundary="committed")
    finally: observer.close()
    events,_=read_events(directory(tmp_path,second))
    assert [e["item_id"] for e in events]==["new"]
    assert capability(directory(tmp_path,second))["processes"][0]["dropped"]==1


def test_file_failure_and_oversize_are_explicit_loss(tmp_path,monkeypatch):
    from app.runtime.diagnostics import memory_pipeline_observation as module
    observer=MemoryPipelineObserver(tmp_path,"process");value=manifest();observer.attach(value)
    try:
        monkeypatch.setattr(module,"EVENT_LIMIT",20)
        with observation.scope(world_id="w",actor_id="a"):
            observation.emit("result",item_id="one")
        observer.flush()
        monkeypatch.setattr(module,"EVENT_LIMIT",16384)
        with observation.scope(world_id="w",actor_id="a"):
            observation.emit("result",item_id="two")
        original=module.Path.open
        event_path=directory(tmp_path,value) / "memory-pipeline" / "events-process-0000.jsonl"
        def failed(path,*args,**kwargs):
            if path == event_path: raise OSError("PRIVATE-SENTINEL")
            return original(path,*args,**kwargs)
        with monkeypatch.context() as file_failure:
            file_failure.setattr(module.Path,"open",failed)
            observer.flush()
    finally: observer.close()
    health=capability(directory(tmp_path,value))["processes"][0]
    assert health["truncated"]==1 and health["failed"]==1 and sum(health["expected"].values())==2


def recorded_files(root):
    return {path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def test_memory_arrivals_wake_existing_writer_once_per_pending_flush(tmp_path):
    wakes = []
    observer = MemoryPipelineObserver(tmp_path, "process", wake=lambda: wakes.append(True))
    observer.attach(manifest())
    try:
        with observation.scope(world_id="w", actor_id="a"):
            for i in range(8):
                observation.emit("result", item_id=str(i), boundary="current")
        assert len(wakes) == 1
        assert not list((directory(tmp_path, manifest()) / "memory-pipeline").glob("events-*"))
        observer.flush()
        with observation.scope(world_id="w", actor_id="a"):
            observation.emit("result", item_id="next", boundary="current")
        assert len(wakes) == 2
    finally:
        observer.close()
    events, damaged = read_events(directory(tmp_path, manifest()))
    assert len(events) == 9 and not damaged
    health = capability(directory(tmp_path, manifest()))["processes"][0]
    assert health["dropped"] == health["dropped_queue_full"] == health["dropped_lock_busy"] == 0


def test_final_flush_disconnects_and_never_rewrites_finished_evidence(tmp_path):
    observer = MemoryPipelineObserver(tmp_path, "process")
    value = manifest()
    observer.attach(value)
    callback = observation._sink
    try:
        with observation.scope(world_id="w", actor_id="a"):
            observation.emit("result", item_id="accepted", boundary="committed")
        observer.flush(final=True)
        assert not observation.enabled()
        events, damaged = read_events(directory(tmp_path, value))
        health = capability(directory(tmp_path, value))["processes"][0]
        assert [event["item_id"] for event in events] == ["accepted"] and not damaged
        assert health["final"] and health["queued"] == 0
        before = recorded_files(tmp_path)
        for _ in range(3):
            callback({"event": "result", "world_id": "w", "actor_id": "a", "item_id": "late"})
            callback({"event": "diagnostic_loss"})
            observer.flush()
            observer.flush(final=True)
            observer.attach(value)  # A completed session cannot be reopened.
        observer.close()
        assert not observation.enabled() and recorded_files(tmp_path) == before
    finally:
        observer.close()


def test_final_flush_drains_an_already_admitted_producer(tmp_path, monkeypatch):
    from app.runtime.diagnostics import memory_pipeline_observation as module
    observer = MemoryPipelineObserver(tmp_path, "process")
    value = manifest()
    observer.attach(value)
    admitted, release, finishing = Event(), Event(), Event()
    drained = Event()
    original = module.safe_event
    admission_lock = observer.lock

    class AdmissionBarrier:
        def acquire(self, blocking=True):
            return admission_lock.acquire(blocking=blocking)

        def release(self):
            admission_lock.release()

        def __enter__(self):
            finishing.set()
            admission_lock.acquire()

        def __exit__(self, *_):
            admission_lock.release()

    observer.lock = AdmissionBarrier()
    take = observer.queue.get_nowait

    def drain():
        drained.set()
        return take()

    monkeypatch.setattr(observer.queue, "get_nowait", drain)

    def blocked(value):
        admitted.set()
        assert release.wait(5)
        return original(value)

    monkeypatch.setattr(module, "safe_event", blocked)
    callback = observation._sink
    producer = Thread(target=lambda: callback({"event": "result", "world_id": "w",
        "actor_id": "a", "item_id": "accepted", "boundary": "committed"}))

    def finish():
        observer.flush(final=True)

    finalizer = Thread(target=finish)
    try:
        producer.start()
        assert admitted.wait(5)
        finalizer.start()
        assert finishing.wait(5)
        assert not drained.is_set(), "final drain started before admission was closed"
    finally:
        release.set()
        producer.join(5)
        finalizer.join(5)
        observer.close()
    assert not producer.is_alive() and not finalizer.is_alive()
    events, damaged = read_events(directory(tmp_path, value))
    health = capability(directory(tmp_path, value))["processes"][0]
    assert not damaged and [event["item_id"] for event in events] == ["accepted"]
    assert health["final"] and health["queued"] == 0
    assert sum(health["expected"].values()) == sum(health["written"].values()) == 1


def test_finished_callback_cannot_deliver_to_a_new_session(tmp_path):
    observer = MemoryPipelineObserver(tmp_path, "process")
    first, second = manifest(), manifest("b")
    observer.attach(first)
    old_callback = observation._sink
    try:
        observer.flush(final=True)
        before = recorded_files(directory(tmp_path, first))
        observer.attach(second)
        assert observation.enabled()
        old_callback({"event": "result", "world_id": "w", "actor_id": "a", "item_id": "old"})
        with observation.scope(world_id="w", actor_id="a"):
            observation.emit("result", item_id="new", boundary="committed")
        observer.close()
        events, damaged = read_events(directory(tmp_path, second))
        assert not damaged and [event["item_id"] for event in events] == ["new"]
        assert recorded_files(directory(tmp_path, first)) == before
    finally:
        observer.close()


def test_failed_final_health_does_not_retry_forever_or_claim_complete(tmp_path, monkeypatch):
    from app.runtime.diagnostics import memory_pipeline_observation as recorder
    observer = MemoryPipelineObserver(tmp_path, "process")
    value = manifest()
    observer.attach(value)
    calls = []

    def failed(path, value):
        calls.append(path)
        raise OSError("synthetic file failure")

    monkeypatch.setattr(recorder, "atomic_json", failed)
    try:
        for _ in range(3):
            observer.flush(final=True)
        observer.close()
        assert len(calls) == 1 and not observation.enabled()
        assert observer.sessions[value["session_id"]]["failed"] == 1
        assert not capability(directory(tmp_path, value))["processes"][0]["final"]
    finally:
        observer.close()
