"""Real owner authentication, CSRF, DTOs, scoped cursors and recovery consumer."""
from dataclasses import replace
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from memory.test_p8_l_q_memory_read_inspector import _fixture, _seed, FRONTEND_HEADERS
from memory.test_activity_situation_contract import NOW, values
from app.domains.memory.models.activity_situation import MemorySituationReceipt, MemorySituationApplyRun
from app.domains.memory.models.items import MemoryItem
from app.domains.social.models.posts import Post
from app.domains.memory.repository.situation_admission import admit
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.memory.situation_runtime import SituationRuntime

PATH = "/api/v1/worlds/q-world/world-characters/q-responding/memory"


def fixture():
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    settings = client.get(PATH + "/settings", headers=FRONTEND_HEADERS).json()
    enabled = client.put(PATH + "/settings", headers=FRONTEND_HEADERS,
        json={"expected_version": settings["version"], "enabled": True, "idempotency_key": "http-enable-memory-001"})
    assert enabled.status_code == 200, enabled.text
    rows = []
    with Session(engine) as db:
        scope = seeded["scope"]
        post = Post(id="recovery-http-post", world_id=scope.world_id,
            author_world_character_id=scope.subject_world_character_id,
            author_character_id="q-responding-character", author_name="responding", title="Daily", body="A calm day.", created_at=NOW)
        db.add(post)
        db.commit()
        for number in range(3):
            manifest, draft, result = values(db, scope, target=post.id, logical=f"http-{number}", call=f"http-{number}")
            source = SituationSources(db).describe(scope, kind="POST", identifier=post.id, delivered=post.body,
                path="/target/body", role="core", ordinal=0, target=post.id)
            row = admit(db, manifest=replace(manifest, sources=(source,)), draft=draft, result=result, now=NOW)
            row.state, row.error_code = "blocked", "situation_source_changed_or_forbidden"
            rows.append(row.sequence)
        db.commit()
    return client, engine, principal, seeded, rows


def test_recovery_api_rejects_foreign_scope_csrf_extra_proof_and_cursor_and_resolves_exact_request():
    client, engine, principal, seeded, rows = fixture()
    body = {"expected_version": 1, "idempotency_key": "http-recheck-test-001"}
    assert client.post(PATH + "/recheck", json=body).status_code == 403
    assert client.post(PATH + "/recheck", headers=FRONTEND_HEADERS, json={**body, "observed": True}).status_code == 422
    principal["user"] = seeded["outsider"]
    assert client.get(PATH + "/unsaved-experiences", headers=FRONTEND_HEADERS).status_code == 404
    principal["user"] = seeded["owner"]
    first = client.get(PATH + "/unsaved-experiences", headers=FRONTEND_HEADERS, params={"limit": 2})
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["blocked_count"] == 3 and len(data["items"]) == 2 and data["next_cursor"]
    assert data["items"][0]["description"] and data["items"][0]["can_discard"]
    assert client.get(PATH + "/unsaved-experiences", headers=FRONTEND_HEADERS, params={"cursor": "invalid"}).status_code == 422
    second = client.get(PATH + "/unsaved-experiences", headers=FRONTEND_HEADERS, params={"cursor": data["next_cursor"]})
    assert second.status_code == 200 and len(second.json()["items"]) == 1
    assert client.post(PATH + f"/situations/{rows[0]}/recheck", headers=FRONTEND_HEADERS,
        json={**body, "expected_receipt_version": 99}).status_code == 409
    accepted = client.post(PATH + "/recheck", headers=FRONTEND_HEADERS, json=body)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["operation"] == "blocked_recheck" and accepted.json()["resolved_request_key"] == body["idempotency_key"]
    runtime = SituationRuntime(sessionmaker(engine))
    assert runtime.tick() == "situation_page_applied"
    response = client.get(PATH + "/processing-settings", headers=FRONTEND_HEADERS, params={"request_key": body["idempotency_key"]})
    assert response.json()["applied_count"] == 3 and response.json()["blocked_count"] == 0
    unknown = client.get(PATH + "/processing-settings", headers=FRONTEND_HEADERS, params={"request_key": "unknown-request-001"})
    assert unknown.json()["run_id"] is None and unknown.json()["applied_count"] == 0
    assert client.post(PATH + "/save", headers=FRONTEND_HEADERS, json=body).status_code == 409
    client.close()
    engine.dispose()


def test_off_discard_works_for_damaged_proof_without_leaking_description_or_reapplying():
    client, engine, principal, seeded, rows = fixture()
    with Session(engine) as db:
        row = db.get(MemorySituationReceipt, rows[0])
        row.content_digest = "0" * 64
        db.commit()
        before = db.scalar(select(func.count()).select_from(MemoryItem))
    settings = client.get(PATH + "/settings", headers=FRONTEND_HEADERS).json()
    assert client.put(PATH + "/settings", headers=FRONTEND_HEADERS,
        json={"expected_version": settings["version"], "enabled": False, "idempotency_key": "http-disable-memory-001"}).status_code == 200
    listed = client.get(PATH + "/unsaved-experiences", headers=FRONTEND_HEADERS).json()
    damaged = next(item for item in listed["items"] if item["receipt_sequence"] == rows[0])
    assert damaged["description"] is None and not damaged["can_recheck"] and damaged["can_discard"]
    assert client.post(PATH + "/recheck", headers=FRONTEND_HEADERS,
        json={"expected_version": 1, "idempotency_key": "http-off-recheck-001"}).status_code == 409
    body = {"expected_receipt_version": 1, "idempotency_key": "http-discard-test-001"}
    path = PATH + f"/situations/{rows[0]}/discard"
    result = client.post(path, headers=FRONTEND_HEADERS, json=body)
    assert result.status_code == 200, result.text
    assert result.json()["result"] == "discarded" and result.json()["blocked_count"] == 2
    assert client.post(path, headers=FRONTEND_HEADERS, json=body).json()["discarded_at"] == result.json()["discarded_at"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MemoryItem)) == before
        assert db.scalar(select(func.count()).select_from(MemorySituationApplyRun)) == 0
        assert db.get(Post, "recovery-http-post").body == "A calm day."
    client.close()
    engine.dispose()


def test_list_reuses_checks_only_within_page_and_rechecks_next_request(monkeypatch):
    from app.domains.memory.service.source_evidence import SqlAlchemyMemorySourceEvidenceReader
    client, engine, principal, seeded, rows = fixture()
    calls = []
    original = SqlAlchemyMemorySourceEvidenceReader.read_evidence
    def read(self, **values):
        calls.append(values["source_id"])
        return original(self, **values)
    monkeypatch.setattr(SqlAlchemyMemorySourceEvidenceReader, "read_evidence", read)
    try:
        first = client.get(PATH + "/unsaved-experiences", headers=FRONTEND_HEADERS).json()
        assert len(first["items"]) == 3 and all(item["description"] for item in first["items"])
        assert calls.count("recovery-http-post") == 1
        calls.clear()
        with Session(engine) as db:
            db.get(Post, "recovery-http-post").report_hidden_at = NOW
            db.commit()
        second = client.get(PATH + "/unsaved-experiences", headers=FRONTEND_HEADERS).json()
        assert second["blocked_count"] == 3
        assert all(item["description"] is None and item["can_discard"] for item in second["items"])
        assert calls.count("recovery-http-post") == 1
    finally:
        client.close()
        engine.dispose()
