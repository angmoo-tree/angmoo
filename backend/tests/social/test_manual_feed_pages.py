"""Root-only keyset pages, scoped cursors and read-only summary projection."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from social.test_l3_owner_manual_social_inbox import _fixture, _seed, _owner_payload, _world_post, FRONTEND_HEADERS
from model_fixture_support import models

BASE = "/api/v1/worlds/world-manual/manual-social"


@pytest.fixture
def feed():
    client, engine, principal = _fixture()
    _seed(engine, principal)
    assert client.post("/api/v1/worlds/world-manual/owner-character", headers=FRONTEND_HEADERS, json=_owner_payload()).status_code == 201
    now = datetime.now(UTC) + timedelta(days=1)
    with Session(engine) as db:
        root = db.get(models.Post, "post-autonomous-target")
        for i in range(65):
            db.add(_world_post(post_id=f"root-{i:03}", author_character_id=root.author_character_id,
                author_world_character_id=root.author_world_character_id, world_id=root.world_id, reply_to_post_id=None,
                created_at=now + timedelta(seconds=i // 3)))
        db.flush()
        for i in range(90):
            db.add(_world_post(post_id=f"reply-{i:03}", author_character_id=root.author_character_id,
                author_world_character_id=root.author_world_character_id, world_id=root.world_id,
                reply_to_post_id="root-064", created_at=now + timedelta(days=1)))
        db.commit()
    yield client, engine, principal
    client.close(); engine.dispose()


def test_pages_are_roots_and_counts_remain_complete_without_writes(feed):
    client, engine, _ = feed
    statements = []
    event.listen(engine, "before_cursor_execute", lambda c, cur, statement, *args: statements.append(statement))
    first = client.get(BASE + "/feed", headers=FRONTEND_HEADERS).json()
    assert first["schema_version"] == "owner-manual-social-feed-v2"
    assert [p["id"] for p in first["items"]] == [f"root-{i:03}" for i in range(64, 34, -1)]
    assert first["items"][0]["reply_count"] == 90
    assert all(p["reply_to_post_id"] is None for p in first["items"])
    next_page = client.get(BASE + "/feed", headers=FRONTEND_HEADERS, params={"cursor": first["next_cursor"]}).json()
    assert [p["id"] for p in next_page["items"]] == [f"root-{i:03}" for i in range(34, 4, -1)]
    last = client.get(BASE + "/feed", headers=FRONTEND_HEADERS, params={"cursor": next_page["next_cursor"]}).json()
    assert not last["has_more"] and last["next_cursor"] is None
    assert len({p["id"] for page in (first, next_page, last) for p in page["items"]}) == 66
    summary = client.get(BASE + "/posts/root-064/summary", headers=FRONTEND_HEADERS).json()
    assert summary["items"] == first["items"][:1]
    assert not any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in statements)
    # Cursor is an ordering boundary, not a dependency on the continued presence of that row.
    with Session(engine) as db:
        db.delete(db.get(models.Post, "root-035")); db.commit()
    assert client.get(BASE + "/feed", headers=FRONTEND_HEADERS, params={"cursor": first["next_cursor"]}).json()["items"] == next_page["items"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"cursor": "!bad"}, {"cursor": "a" * 1025}])
def test_invalid_page_never_becomes_unbounded(feed, params):
    client, _, _ = feed
    assert client.get(BASE + "/feed", headers=FRONTEND_HEADERS, params=params).status_code == 422


def test_summary_rejects_reply_and_foreign_or_missing_root(feed):
    client, _, _ = feed
    for post in ("reply-001", "missing"):
        assert client.get(BASE + f"/posts/{post}/summary", headers=FRONTEND_HEADERS).status_code == 404
