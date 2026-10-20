"""Preparation uses current authorization/settings without Chat work or DB writes."""
from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.runtime.chat.message_composition import configure_chat_services
from app.domains.memory.models.items import MemoryScopeSettingModel
from chat.test_p8_l_d_world_chat_api import _fixture, _seed, FRONTEND_HEADERS


def test_preparation_authorizes_reads_closes_session_then_schedules(deny_external_network):
    client, engine, principal = _fixture()
    owner, outsider, actor = _seed(engine, principal)
    thread = client.post("/api/v1/worlds/world-a/chat/threads", headers=FRONTEND_HEADERS,
                         json={"responding_world_character_id": actor}).json()["thread"]["id"]
    path = f"/api/v1/worlds/world-a/chat/threads/{thread}/memory-search/prepare"
    opened, calls, statements = [], [], []

    @contextmanager
    def sessions():
        with Session(engine) as db:
            opened.append(db)
            try:
                yield db
            finally:
                opened.remove(db)

    def prepare(*, semantic):
        assert not opened
        calls.append(semantic)
        return {"fts": {"status": "preparing", "reason": None},
                "vector": {"status": "disabled", "reason": None}}

    configure_chat_services(client.app, session_factory=sessions,
                            search_runtime=SimpleNamespace(request_preparation=prepare))
    assert client.post(path, json={}).status_code == 403
    assert client.post(path, headers=FRONTEND_HEADERS, json={"query": "not-allowed"}).status_code == 422
    assert client.post(path, headers=FRONTEND_HEADERS, json={}).json()["axes"]["fts"]["status"] == "disabled"
    assert calls == []
    with Session(engine) as db:
        db.add(MemoryScopeSettingModel(id="prepare-memory", owner_id=owner.id, world_id="world-a",
            subject_world_character_id=actor, enabled=True, provider_mode="none", version=1))
        db.commit()

    def record(_conn, _cursor, statement, *_args):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(engine, "before_cursor_execute", record)
    try:
        for _ in range(2):
            response = client.post(path, headers=FRONTEND_HEADERS, json={})
            assert response.status_code == 202
            assert response.json()["thread_id"] == thread
        assert calls == [False, False]  # The shared Runtime merges these signals.
        assert not ({"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE"} & set(statements))
        principal["user"] = outsider
        assert client.post(path, headers=FRONTEND_HEADERS, json={}).status_code == 404
        assert calls == [False, False]
        principal["user"] = None
        assert client.post(path, headers=FRONTEND_HEADERS, json={}).status_code == 401
    finally:
        event.remove(engine, "before_cursor_execute", record)
        client.close()
        engine.dispose()
