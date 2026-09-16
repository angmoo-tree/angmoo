"""SD fault injection: fixed native-process ownership, no provider/network/data."""
import asyncio
import json
import multiprocessing
import os
import sqlite3
import time
from time import monotonic

import pytest


def test_worker_deadline_keeps_last_native_stage_and_does_not_return_late_success():
    observation, token = recording()
    workers = FaultWorkers("slow")
    try:
        with pytest.raises(TimeoutError):
            asyncio.run(workers.search(None, deadline=monotonic()+8))
        terminal = observation.search_trace.payload()["terminals"][0]
        assert terminal["terminal_state"] == "deadline"
        assert terminal["failure"]["failure_code"] == "deadline_exceeded"
        assert terminal["last_observed_stage"] == "nn_query"
        assert terminal["eligible_vector_count"] == 7
        assert terminal["joined"] and not workers.active_processes
    finally:
        current.reset(token)


def test_completed_progress_is_not_replaced_by_stale_terminal_snapshot():
    target = SearchTraceCollector()
    running = SearchStage(axis="vector", stage="nn_query", clock_domain="child",
        state="running", start_ms=0, budget_at_start_ms=1)
    completed = running.model_copy(update={"state": "completed", "end_ms": 1.0, "elapsed_ms": 1.0})
    target.add_stage(completed)
    target.add_stage(running)
    assert target.payload()["stages"][0]["state"] == "completed"

from memory.test_sqlite_vec1 import index

def test_real_vector_details_distinguish_empty_and_observed_generation(index):
    from memory.test_sqlite_vec1 import document, search, SCOPE, PROFILE, A
    from app.domains.memory.contracts.vector_projection import MemoryVectorQuery
    import hashlib
    workers = VectorReadWorkers(database_path=index.database_path, extension_path=index._extension,
        extension_sha256=hashlib.sha256(index._extension.read_bytes()).hexdigest())
    for expected in (0, 1):
        observation, token = recording()
        try:
            result = asyncio.run(workers.search(MemoryVectorQuery(SCOPE, PROFILE, A), deadline=monotonic()+10))
            terminal = observation.search_trace.payload()["terminals"][0]
            assert len(result.hits) == expected
            assert terminal["eligible_vector_count"] == expected
            assert terminal["nn_query_started"] is bool(expected)
            assert terminal["generation_match"] is True
            assert terminal["metadata_status"] == "observed"
            assert terminal["observed_generation"] == "v1"
        finally:
            current.reset(token)
        index.upsert((document(),))

from pydantic import ValidationError

from app.contracts.retrieval_observation import Observation, current
from app.contracts.search_diagnostics import (
    SearchDiagnosticTrace, SearchFailure, SearchTerminal, SearchStage, SearchTraceCollector,
    SearchLineage, bounded_capture, collector, lineage,
)
from app.runtime.memory.worker_diagnostics import ProgressSlots, phase, current_worker
from app.runtime.memory.vector_worker import VectorReadWorkers


def fault_child(pipe, case, query, deadline):
    if case == "exit":
        os._exit(17)
    if case == "eof":
        pipe.close()
        return
    if case == "protocol":
        pipe.pipe.send({"protocol": "wrong"})
        pipe.close()
        return
    if case == "slow":
        current_worker.get().metadata["eligible_vector_count"] = 7
        with phase("nn_query"):
            time.sleep(20)
    if case in {"busy", "locked", "load", "mapping"}:
        stage = "extension_load" if case == "load" else "mapping_read" if case == "mapping" else "db_open"
        with phase(stage):
            if case == "mapping":
                from app.runtime.memory.sqlite_vec1 import MemoryVectorProjectionError
                raise MemoryVectorProjectionError("memory_vector_mapping_missing")
            exc = sqlite3.OperationalError("private-canary SQL password=/private/path")
            exc.sqlite_errorcode = sqlite3.SQLITE_BUSY if case == "busy" else sqlite3.SQLITE_LOCKED if case == "locked" else sqlite3.SQLITE_ERROR
            raise exc
    pipe.send((True, ("fixed-result",)))
    pipe.close()


class FaultWorkers(VectorReadWorkers):
    _child_target = staticmethod(fault_child)

    def __init__(self, case):
        self._slots = asyncio.Semaphore(1)
        self._arguments = (case,)
        self.active_processes = set()


def recording():
    observation = Observation(request_id="fixture", detailed=True)
    return observation, current.set(observation)


@pytest.mark.parametrize("case,expected", [
    ("busy", "sqlite_busy"), ("locked", "sqlite_locked"), ("load", "extension_load_failed"),
    ("mapping", "mapping_missing"), ("eof", "result_eof"), ("protocol", "result_decode_failed"),
])
def test_child_failure_survives_boundaries_without_exception_text(case, expected):
    observation, token = recording()
    workers = FaultWorkers(case)
    try:
        with pytest.raises(Exception):
            asyncio.run(workers.search(None, deadline=monotonic()+10))
        payload = observation.search_trace.payload()
        terminal = payload["terminals"][0]
        assert terminal["failure"]["failure_code"] == expected
        assert terminal["joined"] and not workers.active_processes
        assert "private-canary" not in json.dumps(payload)
        assert "private-canary" not in json.dumps(observation.payload())
    finally:
        current.reset(token)


def test_unexpected_exit_is_not_a_database_error():
    observation, token = recording()
    try:
        with pytest.raises(Exception):
            asyncio.run(FaultWorkers("exit").search(None, deadline=monotonic()+10))
        terminal = observation.search_trace.payload()["terminals"][0]
        assert terminal["terminal_state"] == "unexpected_exit"
        assert terminal["worker_exit_code"] == 17
        assert terminal["last_observed_stage"] in {None, "child_bootstrap"}
    finally:
        current.reset(token)


def test_slot_timeout_and_spawn_failure_are_distinct(monkeypatch):
    observation, token = recording()
    try:
        async def blocked():
            workers = FaultWorkers("ok")
            await workers._slots.acquire()
            try:
                with pytest.raises(TimeoutError):
                    await workers.search(None, deadline=monotonic()+0.03)
            finally:
                workers._slots.release()
        asyncio.run(blocked())
        terminal = observation.search_trace.payload()["terminals"][0]
        assert not terminal["worker_started"]
        assert terminal["failure"]["failure_stage"] == "slot_wait"
        def fail_start(self):
            raise OSError("private-canary start path")
        monkeypatch.setattr(multiprocessing.context.SpawnProcess, "start", fail_start)
        with pytest.raises(OSError):
            asyncio.run(FaultWorkers("ok").search(None, deadline=monotonic()+10))
        terminal = observation.search_trace.payload()["terminals"][0]
        assert terminal["failure"]["failure_code"] == "worker_start_failed"
        assert not terminal["worker_started"]
    finally:
        current.reset(token)


def test_cancel_preserves_last_stage_count_and_cleans_process():
    observation, token = recording()
    workers = FaultWorkers("slow")
    try:
        async def run():
            task = asyncio.create_task(workers.search(None, deadline=monotonic()+12))
            for _ in range(1600):
                if any(s.stage == "nn_query" for s in collector().stages.values()):
                    break
                await asyncio.sleep(.005)
            else:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                pytest.fail("child never reached NN")
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        asyncio.run(run())
        terminal = observation.search_trace.payload()["terminals"][0]
        assert terminal["terminal_state"] == "cancelled"
        assert terminal["last_observed_stage"] == "nn_query"
        assert terminal["nn_query_started"] is True
        assert terminal["eligible_vector_count"] == 7
        assert terminal["joined"] and terminal["terminate_sent"]
        assert observation.search_trace.payload()["coverage"] == "partial"
        assert not workers.active_processes
    finally:
        current.reset(token)


def test_shared_progress_is_bounded_and_never_waits_on_abandoned_lock():
    progress = ProgressSlots(multiprocessing.get_context("spawn"))
    stage = SearchStage(axis="vector", stage="nn_query", clock_domain="child", state="running",
        start_ms=0, budget_at_start_ms=1)
    for _ in range(32):
        assert progress.write(stage.model_dump(mode="json"))
    assert not progress.write(stage.model_dump(mode="json"))
    rows, cursor, _ = progress.read()
    assert len(rows) == cursor == 32
    progress.lock.acquire()
    try:
        started = monotonic()
        assert progress.read() == ([], 0, None)
        assert not progress.write(stage.model_dump(mode="json"))
        assert monotonic()-started < .1
    finally:
        progress.lock.release()


def test_detail_payload_limits_preserve_terminal_and_nulls():
    target = SearchTraceCollector()
    target.terminals["vector"] = SearchTerminal(axis="vector", terminal_state="error",
        failure=SearchFailure(failure_code="mapping_missing", failure_stage="mapping_read"),
        worker_exit_code=-15, terminal_observed=True)
    for i in range(200):
        target.add_edge(SearchLineage(stage="axis", action="returned", document_ref="d1", rank=i))
    target.add_edge(SearchLineage(stage="crg", action="returned", evidence_ref="e1"))
    payload = bounded_capture([{"search_text": "한" * 1500, "normalized_query": "글"*1500}]*24, target.payload())
    assert len(json.dumps(payload, ensure_ascii=True).encode()) <= 65536
    trace = SearchDiagnosticTrace.model_validate(payload["search_trace"])
    assert trace.coverage == "partial"
    assert trace.terminals[0].worker_exit_code == -15
    assert trace.terminals[0].eligible_vector_count is None
    assert trace.terminals[0].failure.failure_code == "mapping_missing"


def test_strict_trace_rejects_unknown_fields_ids_and_nonfinite_values():
    with pytest.raises(ValidationError):
        SearchLineage(stage="axis", action="returned", document_ref="private-real-id")
    with pytest.raises(ValidationError):
        SearchTerminal(axis="vector", terminal_state="error", traceback="private-canary")
    with pytest.raises(ValidationError):
        SearchStage(axis="vector", stage="nn_query", clock_domain="child", state="running",
            start_ms=float("nan"), budget_at_start_ms=1)


def test_success_off_on_has_same_value_and_basic_failure_free_summary():
    outputs = []
    for detailed in (False, True):
        observation = Observation(detailed=detailed)
        token = current.set(observation)
        try:
            outputs.append(asyncio.run(FaultWorkers("ok").search(None, deadline=monotonic()+10)))
            if detailed:
                terminal = observation.search_trace.payload()["terminals"][0]
                assert terminal["terminal_state"] == "success" and terminal["failure"] is None
            else:
                assert observation.search_trace is None
        finally:
            current.reset(token)
    assert outputs == [("fixed-result",), ("fixed-result",)]


def test_aliases_are_request_local_and_never_export_raw_identity():
    observation, token = recording()
    try:
        for i in range(300):
            lineage("axis", "returned", identities={"document_ref": ("d", f"private-canary-{i}")})
        data = observation.search_trace.payload()
        assert data["aliases_dropped"] > 0
        assert "private-canary" not in json.dumps(data)
    finally:
        current.reset(token)


def test_requested_metadata_survives_deadline_before_child_starts():
    from types import SimpleNamespace
    from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
    workers = VectorReadWorkers(database_path=None, extension_path=None,
        extension_sha256=None, generation="expected-generation")
    observation, token = recording()
    try:
        with pytest.raises(TimeoutError):
            asyncio.run(workers.search(SimpleNamespace(profile=EMBEDDING_PROFILE), deadline=monotonic()-1))
        row = observation.search_trace.payload()["terminals"][0]
        assert row["requested_generation"] == "expected-generation"
        assert row["requested_profile"] == EMBEDDING_PROFILE
        assert row["observed_generation"] is None
        assert row["eligible_vector_count"] is None
        assert row["worker_started"] is False
    finally:
        current.reset(token)


@pytest.mark.parametrize("mode", ["mismatch", "missing"])
def test_auxiliary_metadata_does_not_change_search_acceptance(index, mode):
    from memory.test_sqlite_vec1 import document, SCOPE, PROFILE, A
    from app.domains.memory.contracts.vector_projection import MemoryVectorQuery
    from app.runtime.memory.sqlite_vec1 import VectorCancellation
    from app.runtime.memory.worker_diagnostics import WorkerTrace
    index.upsert((document(),))
    with sqlite3.connect(index.database_path) as connection:
        connection.execute("UPDATE projection_profile SET generation='other'" if mode == "mismatch" else "DROP TABLE projection_profile")
    trace = WorkerTrace("vector", monotonic()+10, detailed=True)
    token = current_worker.set(trace)
    try:
        result = index.search(MemoryVectorQuery(SCOPE, PROFILE, A), cancellation=VectorCancellation(monotonic()+10))
        assert len(result.hits) == 1
        assert trace.error is None
        assert trace.metadata["metadata_status"] == ("observed" if mode == "mismatch" else "unavailable")
        if mode == "mismatch":
            assert trace.metadata["generation_match"] is False
    finally:
        current_worker.reset(token)


def test_parallel_requests_keep_trace_and_aliases_isolated():
    async def run():
        async def one(name):
            observation, token = recording()
            try:
                lineage("axis", "returned", identities={"document_ref": ("d", name)})
                result = await FaultWorkers("ok").search(None, deadline=monotonic()+10)
                return result, observation.search_trace
            finally:
                current.reset(token)
        return await asyncio.gather(one("private-first"), one("private-second"))
    first, second = asyncio.run(run())
    assert first[0] == second[0]
    assert first[1] is not second[1]
    assert len(first[1].aliases) == len(second[1].aliases) == 1
    assert first[1].payload()["lineage"][0]["document_ref"] == "d1"
    assert "private" not in json.dumps(first[1].payload())


def test_diagnostic_stage_collection_failure_does_not_change_success(monkeypatch):
    observation, token = recording()
    target = collector()
    monkeypatch.setattr(target, "add_stage", lambda row: (_ for _ in ()).throw(ValueError("fixture")))
    workers = FaultWorkers("ok")
    try:
        assert asyncio.run(workers.search(None, deadline=monotonic()+10)) == ("fixed-result",)
        assert not workers.active_processes
        assert target.stage_dropped > 0
    finally:
        current.reset(token)


def test_embedding_failure_keeps_usage_and_does_not_start_worker():
    from types import SimpleNamespace
    from app.runtime.memory.hybrid_axes import VectorHybridAxis
    class Embedder:
        async def query(self, request, *, deadline):
            exc = TimeoutError("private-provider-message")
            exc.physical_attempts, exc.input_tokens, exc.duration_ms = 1, 12, 9
            raise exc
    class NeverWorkers:
        async def search(self, *args, **kwargs):
            raise AssertionError("worker should not start")
    observation, token = recording()
    try:
        result = asyncio.run(VectorHybridAxis(NeverWorkers(), Embedder()).search(SimpleNamespace(), deadline=monotonic()+10))
        assert result.embedding_usage.logical_calls == 1
        row = observation.search_trace.payload()["terminals"][0]
        assert row["failure"]["failure_stage"] == "embedding"
        assert row["worker_started"] is False
        assert "private-provider" not in json.dumps(observation.search_trace.payload())
    finally:
        current.reset(token)


def test_cleanup_reporting_error_keeps_result_and_releases_process(monkeypatch):
    from multiprocessing.process import BaseProcess
    original = BaseProcess.close
    def close_and_report_error(process):
        original(process)
        raise OSError("private-cleanup-canary")
    monkeypatch.setattr(BaseProcess, "close", close_and_report_error)
    observation, token = recording()
    workers = FaultWorkers("ok")
    try:
        assert asyncio.run(workers.search(None, deadline=monotonic()+10)) == ("fixed-result",)
        row = observation.search_trace.payload()["terminals"][0]
        assert row["cleanup_error_code"] == "cleanup_failed"
        assert row["joined"] and not workers.active_processes
        assert "private-cleanup" not in json.dumps(observation.search_trace.payload())
    finally:
        current.reset(token)
