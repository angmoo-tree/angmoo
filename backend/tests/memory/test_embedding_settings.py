from app.runtime import memory_http
from sqlalchemy.orm import Session
from app.domains.identity.models import LlmCredential
from app.domains.memory.exceptions import MemoryValidationError
from memory.test_p8_l_q_memory_read_inspector import _fixture, _seed, FRONTEND_HEADERS


def test_embedding_setting_requires_scope_csrf_and_version_without_generation(monkeypatch):
    client, engine, principal = _fixture()
    _seed(engine, principal)
    with Session(engine) as db:
        db.add_all([LlmCredential(id=key, owner_id=principal["user"].id,
            provider="google", purpose="agent", model="gemini-3.1-flash-lite",
            auth_profile_id=key, label="Test key") for key in ("shared-key", "another-key")])
        db.commit()
    calls = []
    def validate(db, owner, credential):
        calls.append((owner, credential))
        if credential == "foreign-key":
            raise MemoryValidationError("memory_embedding_credential_unavailable")
    monkeypatch.setattr(memory_http, "validate_embedding_credential", validate)
    path = "/api/v1/worlds/q-world/world-characters/q-responding/memory/embedding-settings"
    initial = client.get(path, headers=FRONTEND_HEADERS)
    assert initial.status_code == 200, initial.text
    assert initial.json()["version"] == 0 and not initial.json()["enabled"]
    body = dict(expected_version=0, enabled=True, provider="google", model="gemini-embedding-2", credential_id="shared-key")
    assert client.put(path, json=body).status_code == 403
    assert client.put(path, json={**body, "credential_id": "foreign-key"}, headers=FRONTEND_HEADERS).status_code == 422
    saved = client.put(path, json=body, headers=FRONTEND_HEADERS)
    assert saved.status_code == 200, saved.text
    assert saved.json()["ready"] and saved.json()["version"] == 1
    profile = saved.json()["profile"]
    assert client.put(path, json=body, headers=FRONTEND_HEADERS).status_code == 409
    changed = client.put(path, json={**body, "expected_version": 1, "credential_id": "another-key"}, headers=FRONTEND_HEADERS)
    assert changed.status_code == 200, changed.text
    assert changed.json()["profile"] == profile
    assert client.put(path.replace("q-responding", "missing"), json=body, headers=FRONTEND_HEADERS).status_code == 404
    assert calls and all(key != "" for _, key in calls)
    client.close()
    engine.dispose()
