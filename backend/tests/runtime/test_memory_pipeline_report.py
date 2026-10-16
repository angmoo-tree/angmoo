"""Independent source denominators and partial diagnostic exports."""
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from app.core import work_observation as observation
from app.runtime.diagnostics.memory_pipeline_observation import MemoryPipelineObserver
from app.runtime.diagnostics.memory_pipeline_report import export_memory, capability, timing
from app.runtime.diagnostics.memory_pipeline_snapshot import snapshot
from runtime.test_memory_pipeline_observation import manifest, directory
from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.test_vector_batch_delivery import populate
from runtime.test_situation_observation import observer_data_root


def test_independent_canonical_denominator_missing_event_and_readonly(runtime_factory,tmp_path,monkeypatch):
    values=manifest();values["started_at"]=(datetime.now(UTC)-timedelta(minutes=1)).isoformat()
    values["world_id"]="recall-world";values["actor_ids"]=["recall-subject"]
    ids=populate(runtime_factory,monkeypatch,7)
    db=runtime_factory.kw["bind"].url.database
    values["database_relative_path"]="canonical.sqlite3"
    with sqlite3.connect(db) as connection:
        before=connection.execute("SELECT id,version,summary FROM memory_items ORDER BY id").fetchall()
    observer=MemoryPipelineObserver(tmp_path,"one");observer.attach(values)
    with observation.scope(world_id="recall-world",actor_id="recall-subject"):
        observation.emit("result",boundary="current",item_id=ids[0])
    observer.close()
    state=snapshot(db,values)
    assert state["status"]=="ok" and len(state["items"])==7
    output=tmp_path/"export"
    coverage=export_memory(directory(tmp_path,values),output,db,values,data_root=tmp_path)
    assert coverage["status"]=="PARTIAL" and coverage["canonical_denominator"]["registered_items"]==7
    assert coverage["canonical_denominator"]["missing_observations"]==6
    assert coverage["unknown_denominator"] is False
    with sqlite3.connect(db) as connection:
        assert before==connection.execute("SELECT id,version,summary FROM memory_items ORDER BY id").fetchall()
    serialized="\n".join(p.read_text() for p in output.rglob("*.json*"))
    assert before[0][2] not in serialized


def test_unknown_old_session_schema_busy_and_corrupt_health(tmp_path):
    value=manifest();path=tmp_path/"canonical.sqlite3"
    with sqlite3.connect(path) as db:db.execute("CREATE TABLE original(id INTEGER)")
    assert snapshot(path,value)["status"]=="unsupported_schema"
    assert capability(tmp_path)["support"]=="unavailable"
    folder=directory(tmp_path,value)/"memory-pipeline";folder.mkdir(parents=True)
    (folder/"health-broken.json").write_text('{"schema":"memory-pipeline-observation.v1"}')
    assert capability(directory(tmp_path,value))["damaged"]==1
    (folder/"health-naive.json").write_text('{"schema":"memory-pipeline-observation.v1","heartbeat_at":"2026-10-16T00:00:00","sequence":0}')
    assert capability(directory(tmp_path,value))["damaged"]==2
    with sqlite3.connect(path) as holder:
        holder.execute("BEGIN EXCLUSIVE")
        assert snapshot(path,value)["status"]=="partial_read_failed"


def test_nested_intervals_and_30s_gap_are_review_not_failure():
    def event(span,operation,boundary,at,parent=None):
        return {"event":"stage","process_instance_id":"one","span_id":span,"operation":operation,
            "boundary":boundary,"monotonic_ns":int(at*1e9),"parent_span_id":parent}
    events=[event("parent","save","start",0),event("child","brief_scope","start",1,"parent"),
        event("child","brief_scope","end",32,"parent"),event("parent","save","end",40)]
    spans,summary=timing(events)
    assert len(spans)==2 and summary["per_operation"]["save"]["max_ms"]==40000
    assert summary["nested_spans_additive"] is False and summary["over_30s_review_count"]==2
    assert "unknown" in summary["attribution"]
    events.pop();assert timing(events)[1]["open_spans"]==1


def test_memory_auxiliary_export_failure_preserves_existing_sns_files(observer_data_root, tmp_path, monkeypatch):
    from app.runtime.diagnostics import sns_observation_report as report
    from app.runtime.diagnostics import memory_pipeline_report as memory_report
    now = datetime.now(UTC)
    value = report.start_session(observer_data_root, world_id="world-1", actor_ids=["actor-1"], now=now)
    report.stop_session(observer_data_root, value["session_id"], now=now+timedelta(seconds=1))
    def failed(*args, **kwargs):
        raise OSError("PRIVATE-SENTINEL")
    monkeypatch.setattr(memory_report, "export_memory", failed)
    output = tmp_path/"failed-memory-export"
    coverage = report.export_session(observer_data_root, value["session_id"], destination=output, now=now+timedelta(seconds=2))
    assert (output/"report.md").is_file() and (output/"situation-evidence-coverage.json").is_file()
    assert coverage["memory_pipeline"]["memory_pipeline_evidence_complete"] is False
    assert coverage["memory_pipeline"]["export_error"] == "memory_pipeline_export_failed"
    assert "PRIVATE" not in (output/"coverage.json").read_text()


def test_contenders_require_matching_database_and_actual_acquire_hold_overlap():
    events = []
    def span(identifier, database, start, acquire, end):
        for event, boundary, at in (("stage", "start", start), ("sqlite", "begin_started", start),
                ("sqlite", "acquired", acquire), ("sqlite", "committed", end), ("stage", "end", end)):
            events.append(dict(event=event, boundary=boundary, monotonic_ns=at, span_id=identifier,
                database_id=database, process_instance_id="process", operation="sqlite_writer"))
    span("holder", "canonical", 1, 2, 20)
    span("waiter", "canonical", 3, 21, 22)
    span("unrelated", "vectors", 4, 5, 19)
    _, report = timing(events)
    assert [(row["span_id"], row["overlap_span_id"]) for row in report["contenders"]] == [("waiter", "holder")]
    assert report["contenders"][0]["causality"] == "overlap_only_not_proven"
    assert report["contenders_truncated"] is False
