from sqlalchemy.orm import Session
from app.runtime import memory_http as memory_routes
from app.domains.memory.models.items import MemoryScopeSettingModel
from memory.test_p8_l_q_memory_read_inspector import _fixture, _seed, FRONTEND_HEADERS


def test_manual_http_scope_consent_versions_replay_and_read_only_progress(monkeypatch):
    client, engine, principal = _fixture()
    _seed(engine, principal)
    readiness = []
    monkeypatch.setattr(memory_routes, "memory_provider", lambda factory, owner, model: readiness.append(model))
    path = "/api/v1/worlds/q-world/world-characters/q-responding/memory"
    saved = client.put(path + "/batch-settings", headers=FRONTEND_HEADERS, json={
        "expected_version": 0, "expected_profile_version": 0, "ai_enabled": True,
        "shutdown_enabled": True, "schedule_enabled": False, "local_time": "22:30",
        "model_id": "gemini-3.1-flash-lite", "consent_version": "memory-selection-consent.v1",
        "idempotency_key": "manual-api-settings"})
    assert saved.status_code == 200, saved.text
    current_setting = client.get(path + "/settings", headers=FRONTEND_HEADERS).json()
    enabled = client.put(path + "/settings", headers=FRONTEND_HEADERS, json={
        "expected_version": current_setting["version"], "enabled": True, "idempotency_key": "manual-api-enable"})
    assert enabled.status_code == 200, enabled.text
    with Session(engine) as db:
        setting = db.query(MemoryScopeSettingModel).filter_by(subject_world_character_id="q-responding").one()
        version = setting.version
    body = dict(expected_version=saved.json()["version"], expected_profile_version=saved.json()["profile_version"],
        expected_scope_version=version, idempotency_key="manual-api-start")
    assert client.post(path + "/batch-run", json=body).status_code == 403
    started = client.post(path + "/batch-run", headers=FRONTEND_HEADERS, json=body)
    assert started.status_code == 202, started.text
    receipt = started.json()["request_id"]
    before = len(readiness)
    replay = client.post(path + "/batch-run", headers=FRONTEND_HEADERS, json=body)
    assert replay.json()["request_id"] == receipt and replay.json()["disposition"] == "reused"
    assert len(readiness) == before
    for _ in range(3):
        read = client.get(path + "/batch-progress", headers=FRONTEND_HEADERS, params={"request_id": receipt})
        assert read.status_code == 200 and read.json()["progress"]["request_id"] == receipt
    assert len(readiness) == before  # reads never resolve credentials or call AI
    assert client.post(path + "/batch-run", headers=FRONTEND_HEADERS,
        json={**body, "expected_version": 999}).status_code == 409
    assert client.get(path.replace("q-world", "other-world") + "/batch-progress",
        headers=FRONTEND_HEADERS, params={"request_id": receipt}).status_code == 404
    assert client.get(path + "/batch-progress", headers=FRONTEND_HEADERS,
        params={"request_id": "unknown-receipt"}).status_code == 404
