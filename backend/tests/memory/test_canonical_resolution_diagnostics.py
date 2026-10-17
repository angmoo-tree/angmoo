import asyncio
from time import monotonic
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.contracts.retrieval_observation import Observation, current
from app.contracts.search_diagnostics import trace_payload
from app.runtime.memory.canonical_worker import CanonicalReadWorker, DeadlineSessionFactory


@pytest.mark.parametrize("mode", ["completed", "deadline", "off"])
def test_resolve_receipts_preserve_observed_cost_on_failure_and_off_is_inert(tmp_path, mode, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'cost.sqlite'}")
    sessions = DeadlineSessionFactory(sessionmaker(engine))
    class Reader:
        def resolve(self, *_):
            with sessions() as db:
                with sessions.phase("revalidate"):
                    if mode == "deadline":
                        db.scalar(text("WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT sum(x) FROM n"))
                    else:
                        db.scalar(text("SELECT 1"))
                with sessions.phase("hydrate"):
                    return db.scalar(text("SELECT 2"))
    worker = CanonicalReadWorker(sessions, Reader())
    if mode == "off":
        def unexpected(*_): raise AssertionError("Detailed progress allocated while OFF")
        monkeypatch.setattr("app.runtime.memory.canonical_worker.ReadProgress", unexpected)
    async def run():
        observation = Observation(request_id="synthetic", detailed=mode != "off")
        token = current.set(observation)
        try:
            if mode == "deadline":
                with pytest.raises(TimeoutError):
                    await worker.resolve_async(None, (), deadline=monotonic()+.15)
            else:
                assert await worker.resolve_async(None, (), deadline=monotonic()+3) == 2
            trace = trace_payload()
            if mode == "off":
                assert trace is None and observation.search_trace is None
            else:
                row, = trace["canonical_reads"]
                assert row["stage"] == "resolve" and row["status"] == mode
                assert row["sql_count"] >= 2 and row["elapsed_ms"] > 0 and row["wait_ms"] >= 0
                assert sum(p["sql_count"] for p in row["phases"]) <= row["sql_count"]
                if mode == "completed":
                    assert row["cleaned"] and row["metrics_complete"]
                    assert [p["stage"] for p in row["phases"]] == ["revalidate", "hydrate"]
                else:
                    assert not row["phases"][0]["completed"]
        finally:
            current.reset(token)
            await worker.stop()
        assert engine.pool.checkedout() == 0
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 3")) == 3
    try: asyncio.run(run())
    finally: engine.dispose()


def test_axis_reasons_survive_canonical_deadline_without_invented_transport_success():
    from app.domains.memory.contracts.hybrid_recall import HybridAxisResult, RecallAxisReceipt, RecallAxisStatus, HybridRecallRequest
    from app.domains.memory.contracts.scope import MemoryScope
    from app.domains.memory.contracts.recall import RecallDocumentKind
    from app.domains.memory.service.hybrid_recall import HybridRecallService
    from memory.test_hybrid_recall import candidate
    class Axis:
        def __init__(self, name): self.name = name
        async def search(self, *_args, **_kwargs):
            return HybridAxisResult(() if self.name == "fts" else (candidate("candidate"),),
                RecallAxisReceipt(self.name, RecallAxisStatus.UNAVAILABLE if self.name == "fts" else RecallAxisStatus.READY,
                    self.name != "fts", 0 if self.name == "fts" else 1, 0, "fts_preparing" if self.name == "fts" else None))
    class Canonical:
        async def resolve_async(self, *_args, **_kwargs): raise TimeoutError("canonical_read_deadline")
    async def run():
        observation = Observation(request_id="axes", detailed=True)
        token = current.set(observation)
        try:
            service = HybridRecallService(fts=Axis("fts"), vector=Axis("vector"), canonical=Canonical())
            request = HybridRecallRequest("request", "call", "a"*64, MemoryScope("o", "w", "s"), "query", "profile", (RecallDocumentKind.MEMORY_ITEM,))
            with pytest.raises(TimeoutError): await service.execute(request, deadline=monotonic()+1)
            rows = {row["axis"]: row for row in trace_payload()["terminals"]}
            assert rows["fts"]["axis_status"] == "unavailable" and rows["fts"]["axis_reason"] == "fts_preparing"
            assert rows["vector"]["axis_status"] == "ready"
            assert all(row["terminal_state"] != "completed" for row in rows.values())
        finally: current.reset(token)
    asyncio.run(run())


def test_queued_expired_read_has_unknown_execution_cost_and_does_not_open_session(tmp_path):
    from threading import Event
    from memory.test_hybrid_read_snapshot import wait_entered
    entered, release = Event(), Event()
    engine = create_engine(f"sqlite:///{tmp_path / 'queued.sqlite'}")
    sessions = DeadlineSessionFactory(sessionmaker(engine))
    invoked = []
    class Reader:
        def resolve(self, name, _rows):
            invoked.append(name)
            if name == "first":
                entered.set()
                assert release.wait(5)
            with sessions() as db: return db.scalar(text("SELECT 1"))
    worker = CanonicalReadWorker(sessions, Reader())
    async def run():
        first = asyncio.create_task(worker.resolve_async("first", (), deadline=monotonic()+5))
        await wait_entered(entered)
        token = current.set(Observation(request_id="queued", detailed=True))
        try:
            with pytest.raises(TimeoutError): await worker.resolve_async("second", (), deadline=monotonic()+.05)
            row, = trace_payload()["canonical_reads"]
            assert row["status"] == "deadline" and not row["metrics_complete"]
            assert all(row[key] is None for key in ("sql_count", "elapsed_ms", "wait_ms", "cleaned"))
        finally:
            current.reset(token)
            release.set()
            assert await first == 1
            await worker.stop()
        assert invoked == ["first"] and engine.pool.checkedout() == 0
    try: asyncio.run(run())
    finally: engine.dispose()
