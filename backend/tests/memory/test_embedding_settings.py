from sqlalchemy.orm import Session
from app.domains.identity.service import world_credentials
from app.domains.identity.schemas import WorldCredentialWrite
from memory.test_p8_l_q_memory_read_inspector import _fixture, _seed, FRONTEND_HEADERS


def test_embedding_setting_requires_scope_csrf_and_version_without_generation(monkeypatch):
    client, engine, principal = _fixture()
    _seed(engine, principal)
    scope = dict(owner_id=principal["user"].id, world_id="q-world", world_character_id="q-responding", purpose="embedding")
    with Session(engine) as db:
        world_credentials.save(db, **scope, data=WorldCredentialWrite(expected_revision=0, provider="google", model="gemini-embedding-2", thinking_level=None, api_key="synthetic-own-embedding-key"))
        db.commit()
    path = "/api/v1/worlds/q-world/world-characters/q-responding/memory/embedding-settings"
    initial = client.get(path, headers=FRONTEND_HEADERS)
    assert initial.status_code == 200, initial.text
    assert initial.json()["version"] == 0 and not initial.json()["enabled"]
    body = dict(expected_version=0, enabled=True, provider="google", model="gemini-embedding-2", credential_id=None)
    assert client.put(path, json=body).status_code == 403
    # No key picker is accepted, even for a same-owner key or when search is OFF.
    for name in ("shared-key", "another-key", "foreign-key"):
        for enabled in (True, False):
            response = client.put(path, json={**body, "credential_id": name, "enabled": enabled}, headers=FRONTEND_HEADERS)
            assert response.status_code == 422
    saved = client.put(path, json=body, headers=FRONTEND_HEADERS)
    assert saved.status_code == 200, saved.text
    assert saved.json()["ready"] and saved.json()["version"] == 1
    assert saved.json()["credential_id"] is None
    profile = saved.json()["profile"]
    assert client.put(path, json=body, headers=FRONTEND_HEADERS).status_code == 409
    with Session(engine) as db:
        world_credentials.save(db, **scope, data=WorldCredentialWrite(expected_revision=1, provider="google", model="gemini-embedding-2", thinking_level=None, api_key="rotated-own-embedding-key"))
        db.commit()
    changed = client.put(path, json={**body, "expected_version": 1}, headers=FRONTEND_HEADERS)
    assert changed.status_code == 200, changed.text
    assert changed.json()["profile"] == profile
    assert client.put(path.replace("q-responding", "missing"), json=body, headers=FRONTEND_HEADERS).status_code == 404
    assert client.get(path.replace("q-responding", "missing"), headers=FRONTEND_HEADERS).status_code == 404
    client.close()
    engine.dispose()
