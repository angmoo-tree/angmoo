"""Diagnostics cannot change retrieval, disclose bodies, or cross request scopes."""
import asyncio
from datetime import UTC, datetime, timedelta
import json
from statistics import quantiles
from time import perf_counter

import pytest
from sqlalchemy import select

from app.contracts.retrieval_observation import Observation, current, detail, observe
from app.domains.chat.models import ChatRetrievalDiagnostic
from app.domains.chat.repository import retrieval_diagnostics as repository
from app.domains.chat.service.diagnostic_capture import DiagnosticCapture
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from app.runtime.chat.generation_workflows import SqlAlchemyResponseWorkflowUnitOfWork
from test_p8_l_p_evidence_response_streaming import (
    response_session, _request, _workflow, _Generator, _collect, _command,
)


def test_basic_is_bounded_and_final_evidence_survives_overflow():
    observation = Observation(detailed=False)
    token = current.set(observation)
    try:
        for _ in range(200):
            observe("search", method="fts5", returned=3, search_text="PRIVATE BODY", api_key="PRIVATE KEY")
            detail(search_text="PRIVATE BODY")
        observe("crg_input", items=2)
    finally:
        current.reset(token)
    payload = observation.payload()
    serialized = json.dumps(payload)
    assert len(serialized.encode()) <= 16384
    assert "PRIVATE" not in serialized
    assert not observation.details
    assert payload["omitted_events"] > 0
    assert payload["events"][-1] == {"event": "crg_input", "items": 2}


def test_capture_requires_admission_and_is_scoped_bounded_and_ephemeral():
    capture = DiagnosticCapture()
    scope = ("owner", "world", "thread")
    other = ("owner", "other-world", "thread")
    capture.admit(scope, "old")
    capture.configure(scope, True)
    assert not capture.active(scope, "old")
    for index in range(11):
        capture.admit(scope, str(index))
    assert capture.active(scope, "9")
    assert not capture.active(scope, "10")
    capture.store(scope, "9", [{"search_text": "synthetic private query"}])
    assert capture.read(other, "9") is None
    assert capture.read(scope, "9")
    assert DiagnosticCapture().read(scope, "9") is None
    capture.configure(scope, False)
    assert capture.read(scope, "9") is None
    assert not capture.active(scope, "9")
    capture.configure(scope, True)
    capture.admit(scope, "expired")
    capture._admitted["expired"] = (scope, datetime.now(UTC) - timedelta(seconds=1))
    assert not capture.active(scope, "expired")


@pytest.mark.parametrize("route", list(RetrievalRoute))
def test_real_checkpoint_saves_diagnostics_without_stream_changes(response_session, route):
    record = _request(response_session, route)
    response_session.commit()
    generator = _Generator()
    workflow = _workflow(response_session, route, generator)
    workflow._unit_of_work = SqlAlchemyResponseWorkflowUnitOfWork(response_session)
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type.value == "completed"
    assert len(generator.requests) == 1
    result = repository.read(response_session, record.request_id)
    assert result["status"] == "available"
    names = [row["event"] for row in result["record"]["events"]]
    assert "router" in names and "crg_input" in names and "crg_completed" in names
    assert "오늘은" not in json.dumps(result, ensure_ascii=False)
    assert all("diagnostic" not in json.dumps(event.payload) for event in events)
    assert current.get() is None


def test_diagnostic_savepoint_failure_does_not_fail_chat(response_session, monkeypatch):
    record = _request(response_session, RetrievalRoute.CANONICAL)
    response_session.commit()
    workflow = _workflow(response_session, RetrievalRoute.CANONICAL, _Generator())
    workflow._unit_of_work = SqlAlchemyResponseWorkflowUnitOfWork(response_session)
    def fail(*args):
        raise RuntimeError("diagnostic-only failure")
    monkeypatch.setattr(repository, "save", fail)
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type.value == "completed"
    assert response_session.is_active


def test_retention_and_expiry_do_not_change_request(response_session):
    record = _request(response_session, RetrievalRoute.CANONICAL)
    response_session.commit()
    observation = Observation(request_id=record.request_id)
    repository.save(response_session, observation)
    response_session.commit()
    row = response_session.get(ChatRetrievalDiagnostic, record.request_id)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    response_session.commit()
    assert repository.read(response_session, record.request_id)["status"] == "expired"
    assert repository.read(response_session, "unknown")["status"] == "not_recorded"


def test_quota_retains_at_most_1000_and_keeps_canonical_requests(response_session):
    from sqlalchemy import insert, func
    from app.domains.chat.models import ChatResponseRequest
    record = _request(response_session, RetrievalRoute.CANONICAL)
    response_session.commit()
    original = response_session.get(ChatResponseRequest, record.request_id)
    template = {column.name: getattr(original, column.name) for column in ChatResponseRequest.__table__.columns}
    requests, diagnostics = [], []
    expiry = datetime.now(UTC) + timedelta(days=1)
    for index in range(1001):
        identifier = f"quota-{index}"
        requests.append({**template, "request_id": identifier, "response_slot_id": identifier, "idempotency_key": identifier})
        diagnostics.append({"request_id": identifier, "expires_at": expiry, "payload_bytes": 2, "payload_json": "{}"})
    response_session.execute(insert(ChatResponseRequest), requests)
    response_session.execute(insert(ChatRetrievalDiagnostic), diagnostics)
    response_session.commit()
    repository.save(response_session, Observation(request_id=record.request_id))
    response_session.commit()
    assert response_session.scalar(select(func.count()).select_from(ChatRetrievalDiagnostic)) == 1000
    assert response_session.scalar(select(func.count()).select_from(ChatResponseRequest)) == 1002


def test_v10_to_v11_adds_only_empty_diagnostics_table():
    from sqlalchemy import create_engine
    from app.runtime.persistence.sqlite_schema import build_sqlite_v10_metadata, create_schema_version_table, sqlite_schema_contract_digest
    from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
    from app.runtime.migrations.sqlite_versions.v10_to_v11_chat_diagnostics import capture_delta, upgrade, verify_delta
    with create_engine("sqlite://").begin() as connection:
        create_schema_version_table(connection)
        build_sqlite_v10_metadata().create_all(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(10).schema_digest
        before = capture_delta(connection)
        upgrade(connection)
        verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(11).schema_digest


def test_diagnostic_http_auth_scope_origin_and_opt_in():
    from test_p8_l_d_world_chat_api import _fixture, _seed, FRONTEND_HEADERS
    from app.domains.chat.router.retrieval_diagnostics import router
    client, engine, principal = _fixture()
    client.app.include_router(router, prefix="/api/v1")
    owner, outsider, responding = _seed(engine, principal)
    created = client.post("/api/v1/worlds/world-a/chat/threads", headers=FRONTEND_HEADERS,
                          json={"responding_world_character_id": responding})
    thread = created.json()["thread"]["id"]
    url = f"/api/v1/worlds/world-a/chat/threads/{thread}/diagnostics"
    result = client.get(url)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["status"] == "not_recorded"
    assert result.json()["capture"]["enabled"] is False
    assert client.put(url+"/capture", json={"enabled": True}, headers={"Origin": "https://evil.example"}).status_code == 403
    result = client.put(url+"/capture", json={"enabled": True}, headers=FRONTEND_HEADERS)
    assert result.status_code == 200 and result.json()["remaining"] == 10
    assert client.put(url+"/capture", json={"enabled": "true"}, headers=FRONTEND_HEADERS).status_code == 422
    principal["user"] = outsider
    assert client.get(url).status_code == 403
    principal["user"] = owner
    assert client.get(url.replace("world-a", "world-b")).status_code == 404
    assert client.get(url+"?request_id=other-request").status_code == 404
    assert client.delete(url+"/capture", headers=FRONTEND_HEADERS).json()["enabled"] is False
    principal["user"] = None
    assert client.get(url).status_code == 401
    client.close()
    engine.dispose()


def test_collector_and_existing_checkpoint_cost_100_samples(response_session):
    record = _request(response_session, RetrievalRoute.CANONICAL)
    response_session.commit()
    samples = []
    for index in range(110):
        observation = Observation(request_id=record.request_id)
        start = perf_counter()
        token = current.set(observation)
        try:
            for step in range(6):
                observe("step", step=step, queries=1, executed=True)
                observe("validated_result", accepted=3, excluded=1)
            observe("crg_input", items=4)
            SqlAlchemyResponseWorkflowUnitOfWork(response_session).checkpoint()
        finally:
            current.reset(token)
        if index >= 10:
            samples.append((perf_counter() - start) * 1000)
    p95 = quantiles(samples, n=20)[18]
    print(f"diagnostic_collect_serialize_save_p95_ms={p95:.3f}")
    assert len(list(response_session.scalars(select(ChatRetrievalDiagnostic)))) == 1
    # A regression ceiling, not a claimed target for another machine/disk.
    assert p95 < 100
