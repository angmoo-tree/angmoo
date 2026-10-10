"""Explicit trigger, retry, HTTP scope and provider-free runtime regression."""
from datetime import UTC, datetime, timedelta
from dataclasses import replace
import asyncio
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from memory.test_activity_situation_contract import stack, values, NOW
from memory.test_activity_situation_application import real_source, receipt
from app.domains.memory.models.activity_situation import MemorySituationApplyRun, MemorySituationReceipt, MemorySituationProcessingSetting
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
from app.domains.memory.exceptions import MemoryConflictError
from app.runtime.memory.situation_runtime import SituationRuntime

def test_explicit_retry_retains_original_cutoff(stack):
    db, scope, setting, _ = stack
    get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
    manifest, draft, result = values(db, scope)
    admit(db, manifest=manifest, draft=draft, result=result, now=NOW)
    first = request_run(db, setting, trigger="manual", request_key="first-request-001", expected_version=1, now=NOW)
    run = db.get(MemorySituationApplyRun, first.run_id)
    cutoff = run.cutoff_sequence
    run.state, run.error_code = "error", "memory_capacity_reached"
    m, d, r = values(db, scope, logical="late", target="late", call="late")
    admit(db, manifest=m, draft=d, result=r, now=NOW)
    db.commit()
    replay = request_run(db, setting, trigger="manual", request_key="first-request-001", expected_version=1, now=NOW)
    db.refresh(run)
    assert replay.run_id == first.run_id and run.state == "deferred" and run.cutoff_sequence == cutoff
    other = request_run(db, setting, trigger="quit", request_key="quit-request-0001", expected_version=1, now=NOW)
    assert other.run_id == run.id and run.cutoff_sequence == cutoff

def test_runtime_does_not_flush_before_due_and_restarts_started_manual_without_provider(stack, monkeypatch):
    db, scope, setting, _ = stack
    post = real_source(db, scope)
    row = receipt(db, scope, post)
    get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
    db.commit()
    runtime = SituationRuntime(sessionmaker(bind=db.bind))
    runtime.prepare()
    assert runtime.tick() == "memory_batch_queue_empty"
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0
    accepted = request_run(db, setting, trigger="manual", request_key="manual-restart-001", expected_version=1, now=NOW)
    db.commit()
    # Claim was committed but the process disappeared before application.
    claim_run(db, accepted.run_id, now=datetime.now(UTC) - timedelta(seconds=60))
    db.commit()
    restarted = SituationRuntime(sessionmaker(bind=db.bind))
    assert restarted.tick() == "situation_page_applied"
    db.expire_all()
    assert db.get(MemorySituationReceipt, row.sequence).state == "applied"
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 1
    assert restarted.tick() == "memory_batch_queue_empty"

def test_due_and_quit_share_bounded_consumer_and_no_new_arrivals_in_cutoff(stack, monkeypatch):
    db, scope, setting, _ = stack
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(minutes=2)
    monkeypatch.setattr("app.runtime.memory.situation_runtime.datetime", Clock)
    config = get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
    config.daily_enabled, config.next_due_at = True, NOW + timedelta(minutes=1)
    receipt(db, scope, real_source(db, scope))
    db.commit()
    runtime = SituationRuntime(sessionmaker(bind=db.bind))
    runtime.prepare()
    db.expire_all()
    run = db.scalar(select(MemorySituationApplyRun))
    assert run.trigger == "scheduled"
    cutoff = run.cutoff_sequence
    runtime.prepare(shutdown=True)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(MemorySituationApplyRun)) == 1
    assert db.get(MemorySituationApplyRun, run.id).cutoff_sequence == cutoff
    assert runtime.tick() == "situation_page_applied"
    runtime.prepare(shutdown=True)
    assert runtime.tick() == "memory_batch_queue_empty"

def test_http_save_authorization_versions_empty_replay_and_no_implicit_work(monkeypatch):
    from memory.test_p8_l_q_memory_read_inspector import _fixture, _seed, FRONTEND_HEADERS
    client, engine, principal = _fixture()
    _seed(engine, principal)
    path = "/api/v1/worlds/q-world/world-characters/q-responding/memory"
    initial = client.get(path + "/processing-settings", headers=FRONTEND_HEADERS)
    assert initial.status_code == 200, initial.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MemorySituationProcessingSetting)) == 0
    body = dict(expected_version=initial.json()["version"], idempotency_key="manual-http-empty-001")
    assert client.post(path + "/save", json=body).status_code == 403
    assert client.post(path.replace("q-world", "other-world") + "/save", headers=FRONTEND_HEADERS, json=body).status_code == 404
    setting = client.get(path + "/settings", headers=FRONTEND_HEADERS).json()
    enabled = client.put(path + "/settings", headers=FRONTEND_HEADERS, json=dict(expected_version=setting["version"], enabled=True, idempotency_key="enable-situation-http"))
    assert enabled.status_code == 200, enabled.text
    saved = client.post(path + "/save", headers=FRONTEND_HEADERS, json=body)
    assert saved.status_code == 200 and saved.json()["result"] == "empty", saved.text
    assert client.post(path + "/save", headers=FRONTEND_HEADERS, json=body).json()["result"] == "empty"
    assert saved.json()["resolved_request_key"] == body["idempotency_key"]
    from sqlalchemy import event
    statements = []
    def capture_read(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", capture_read)
    try:
        resolved = client.get(path + "/processing-settings", headers=FRONTEND_HEADERS,
            params={"request_key": body["idempotency_key"]})
        assert resolved.status_code == 200
        assert resolved.json()["resolved_request_key"] == body["idempotency_key"]
        assert resolved.json()["result"] == "empty"
        unknown = client.get(path + "/processing-settings", headers=FRONTEND_HEADERS,
            params={"request_key": "unknown-save-request"})
        assert unknown.status_code == 200 and unknown.json()["resolved_request_key"] is None
        assert unknown.json()["result"] is None
        assert client.get(path.replace("q-world", "other-world") + "/processing-settings",
            headers=FRONTEND_HEADERS, params={"request_key": body["idempotency_key"]}).status_code == 404
        assert client.get(path + "/processing-settings", headers=FRONTEND_HEADERS,
            params={"request_key": "short"}).status_code == 422
    finally:
        event.remove(engine, "before_cursor_execute", capture_read)
    assert statements and all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    changed = client.put(path + "/processing-settings", headers=FRONTEND_HEADERS, json={**body,
        "idempotency_key": "http-config-001", "daily_enabled": True, "local_time": "22:30", "shutdown_apply_enabled": False})
    assert changed.status_code == 200, changed.text
    assert client.post(path + "/save", headers=FRONTEND_HEADERS, json={**body, "idempotency_key": "stale-http-001"}).status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MemorySituationApplyRun)) == 0


@pytest.mark.parametrize("has_earlier", [False, True])
def test_missed_due_saves_only_receipts_captured_by_that_due(stack, has_earlier):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    config = get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
    due = NOW + timedelta(seconds=30)
    config.daily_enabled, config.next_due_at = True, due
    earlier = receipt(db, scope, post) if has_earlier else None
    manifest, draft, result = values(db, scope, logical="after-due", target=post.id, call="after-due")
    from app.runtime.memory.situation_sources import SituationSources
    source = SituationSources(db).describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/target/body", role="core", ordinal=0, target=post.id)
    later = admit(db, manifest=replace(manifest, sources=(source,)), draft=draft,
        result=result, now=NOW + timedelta(seconds=60))
    accepted = request_run(db, setting, trigger="scheduled", request_key="missed-daily-001",
        expected_version=1, now=NOW + timedelta(minutes=5))
    assert accepted.result_code == ("accepted" if has_earlier else "empty")
    if has_earlier:
        run = db.get(MemorySituationApplyRun, accepted.run_id)
        assert run.cutoff_sequence == earlier.sequence
        assert datetime.fromisoformat(run.settings_snapshot["cutoff_at"]) == due
        token = claim_run(db, run.id, now=NOW + timedelta(minutes=5))
        from app.domains.memory.repository.situation_apply import apply_page
        apply_page(db, memory, SituationSources(db), run_id=run.id, token=token,
            now=NOW + timedelta(minutes=5))
        assert earlier.state == "applied" and run.state == "completed"
    assert later.state == "pending"
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == int(has_earlier)
    assert config.next_due_at > NOW + timedelta(minutes=5)
    # A later explicit save remains eligible for the receipt left behind.
    manual = request_run(db, setting, trigger="manual", request_key="after-missed-save",
        expected_version=1, now=NOW + timedelta(minutes=6))
    assert db.get(MemorySituationApplyRun, manual.run_id).cutoff_sequence == later.sequence


def test_unexpected_apply_failure_keeps_receipt_and_stops_background_retry(stack, monkeypatch):
    db, scope, setting, _ = stack
    saved = receipt(db, scope, real_source(db, scope))
    get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
    accepted = request_run(db, setting, trigger="manual", request_key="failed-page-0001", expected_version=1, now=NOW)
    db.commit()
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic interrupted page")
    monkeypatch.setattr("app.runtime.memory.situation_runtime.apply_page", fail)
    runtime = SituationRuntime(sessionmaker(bind=db.bind))
    assert runtime.tick() == "situation_apply_failed"
    assert runtime.tick() == "memory_batch_queue_empty"
    db.expire_all()
    run = db.get(MemorySituationApplyRun, accepted.run_id)
    assert run.state == "error" and run.cursor == 0
    assert db.get(MemorySituationReceipt, saved.sequence).state == "pending"
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0


def test_two_file_backed_requesters_coalesce_and_only_one_claims(stack, tmp_path):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    db, scope, setting, _ = stack
    receipt(db, scope, real_source(db, scope))
    get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
    db.commit()
    path = tmp_path / "concurrent.sqlite3"
    with sqlite3.connect(path) as destination:
        db.connection().connection.driver_connection.backup(destination)
    engine = create_engine(f"sqlite:///{path}")
    factory = sessionmaker(engine)
    barrier = Barrier(2)
    def submit(number):
        barrier.wait()
        with factory() as current:
            accepted = request_run(current, setting, trigger="manual", request_key=f"concurrent-save-{number}", expected_version=1, now=NOW)
            current.commit()
            return accepted.run_id
    with ThreadPoolExecutor(2) as pool:
        run_ids = list(pool.map(submit, (1, 2)))
    assert run_ids[0] == run_ids[1]
    barrier = Barrier(2)
    def claim(_):
        barrier.wait()
        with factory() as current:
            token = claim_run(current, run_ids[0], now=NOW)
            current.commit()
            return token
    with ThreadPoolExecutor(2) as pool:
        tokens = list(pool.map(claim, (1, 2)))
    assert sum(token is not None for token in tokens) == 1
    engine.dispose()


@pytest.mark.parametrize("slow", [False, True])
def test_native_quit_applies_receipts_and_fences_slow_search_without_generation(stack, slow, tmp_path):
    from app.runtime.memory.batch_runtime import MemoryBatchRuntime
    from app.runtime.memory.shutdown import MemoryShutdownCoordinator
    db, scope, setting, _ = stack
    saved = receipt(db, scope, real_source(db, scope))
    get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
    db.commit()
    def forbidden(*args):
        raise AssertionError("quit must not generate new descriptions or relationship reviews")
    import sqlite3
    from sqlalchemy import create_engine
    path = tmp_path / "native-quit.sqlite3"
    with sqlite3.connect(path) as destination:
        db.connection().connection.driver_connection.backup(destination)
    engine = create_engine(f"sqlite:///{path}")
    factory = sessionmaker(engine)
    runtime = MemoryBatchRuntime(factory, forbidden,
        generation_policy="activity_situation", idle_work=forbidden)
    class Search:
        fenced = False
        async def wait(self, situations):
            if slow:
                await asyncio.Event().wait()
            return True
        def fence(self):
            self.fenced = True
    search = Search()
    coordinator = MemoryShutdownCoordinator(runtime, search=search, budget_seconds=1.2)
    async def close():
        coordinator.start()
        await asyncio.wait_for(coordinator.task, timeout=3)
    asyncio.run(close())
    assert coordinator.status() == {"phase": "EXIT_READY", "deferred": slow}
    assert search.fenced
    with factory() as current:
        assert current.get(MemorySituationReceipt, saved.sequence).state == "applied"
    asyncio.run(runtime.stop())
    engine.dispose()
