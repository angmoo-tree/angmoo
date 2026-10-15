"""Bulk read through real HTTP and file SQLite; no provider or user data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from types import SimpleNamespace
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, insert, select
from model_fixture_support import models
from social.test_world_user_notifications import (
    WORLD, USER, ME, ACTOR, factory, service, owner_post, reply,
    clone_world_profiles, seed_world_activity,
    canonical_feed_like,
)
from app.core.sqlite_concurrency import run_sqlite_session_immediate, SqliteRetryPolicy
from app.domains.social import dependencies, router_world_notifications as http
from app.domains.social.contracts.world_notifications import WorldNotificationError
from app.runtime.social.composition import configure_social_runtime


def seed_many(factory, count, prefix="bulk"):
    """Bounded synthetic setup; delivery writers are covered by the existing suite."""
    root = owner_post(factory)
    if count:
        with factory() as db:
            sources = [dict(id=f"{prefix}-source-{i}", world_id=WORLD, author_world_character_id=ACTOR,
                author_character_id="social-uow-autonomous-character", author_name="Mango", title="Reply",
                body="Synthetic reply", post_type="reply", visibility="public", reply_to_post_id=root) for i in range(count)]
            db.execute(insert(models.Post), sources)
            db.execute(insert(models.Notification), [dict(world_id=WORLD, recipient_world_character_id=ME,
                recipient_character_id="social-uow-owner-character", actor_world_character_id=ACTOR,
                actor_character_id="social-uow-autonomous-character", notification_type="reply",
                post_id=root, source_post_id=row["id"]) for row in sources])
            db.commit()
    return root


def read_all(factory, expected=ME):
    with factory() as db:
        return run_sqlite_session_immediate(db, lambda: service(db).mark_all_read(
            world_id=WORLD, user_id=USER, recipient_world_character_id=expected))


def application(factory):
    app = FastAPI()
    configure_social_runtime(app)
    app.include_router(http.router, prefix="/api/v1")
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[dependencies.get_db] = database
    app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(id=USER)
    return app


@pytest.mark.parametrize("count", [0, 1, 41])
def test_bulk_updates_all_pages_once_and_preserves_the_first_read(factory, count):
    seed_many(factory, count)
    first_id = first_time = None
    with factory() as db:
        if count > 1:
            first_id = db.scalar(select(models.Notification.id).order_by(models.Notification.id))
            service(db).mark_read(world_id=WORLD, user_id=USER, notification_id=first_id)
            db.commit()
            first_time = db.get(models.Notification, first_id).read_at
        events_before = db.scalar(select(func.count(models.SocialEvent.id)))
        relationships_before = db.scalar(select(func.count(models.RelationshipState.id)))
    sql, commits = [], []
    engine = factory.kw["bind"]
    def record(_connection, _cursor, statement, *_):
        sql.append(statement)
    def committed(_connection):
        commits.append(True)
    event.listen(engine, "before_cursor_execute", record)
    event.listen(engine, "commit", committed)
    try:
        result = read_all(factory)
    finally:
        event.remove(engine, "before_cursor_execute", record)
        event.remove(engine, "commit", committed)
    assert result.marked_count == count - bool(first_id)
    assert result.unread_count == 0
    assert len(commits) == 1
    assert sum(bool(re.search(r"\bUPDATE notifications SET\b", statement, re.I)) for statement in sql) == bool(count)
    assert not any("RETURNING" in statement.upper() for statement in sql)
    assert (result.read_at is None) == (count == 0)
    assert (result.through_notification_id is None) == (count == 0)
    with factory() as db:
        rows = list(db.scalars(select(models.Notification)))
        assert all(row.read_at is not None and row.handled_at is None and row.handling_outcome is None for row in rows)
        if first_id:
            assert db.get(models.Notification, first_id).read_at == first_time
        page = service(db).page(world_id=WORLD, user_id=USER)
        assert page.unread_count == 0 and all(row.read_at for row in page.items)
        if count > 20:
            assert all(row.read_at for row in service(db).page(world_id=WORLD, user_id=USER, cursor=page.next_cursor).items)
        assert db.scalar(select(func.count(models.SocialEvent.id))) == events_before
        assert db.scalar(select(func.count(models.RelationshipState.id))) == relationships_before
    again = read_all(factory)
    assert again.marked_count == 0 and again.unread_count == 0 and again.read_at is None


def test_bulk_scope_does_not_include_other_worlds_and_rejects_profile_changes(factory):
    seed_many(factory, 2)
    clone_world_profiles(factory, "other-world")
    seed_world_activity(factory, "other-world", key="bulk-other")
    with pytest.raises(WorldNotificationError, match="notification_scope_changed"):
        read_all(factory, "owner-other-world")
    with factory() as db:
        assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 2
    assert read_all(factory).marked_count == 2
    with factory() as db:
        assert service(db).count(world_id="other-world", user_id=USER).unread_count == 1


@pytest.mark.parametrize("field", ["post_id", "source_post_id"])
def test_bulk_rejects_a_cross_world_target_even_when_its_post_is_visible(factory, field):
    seed_many(factory, 1)
    clone_world_profiles(factory, "foreign-world")
    source = seed_world_activity(factory, "foreign-world", key=f"foreign-{field}")
    with factory() as db:
        row = db.scalar(select(models.Notification).where(models.Notification.world_id == WORLD))
        setattr(row, field, source)
        db.commit()
        assert service(db).page(world_id=WORLD, user_id=USER).items == []
    assert read_all(factory).marked_count == 0


@pytest.mark.parametrize("action", ["like", "repost", "follow"])
def test_bulk_preserves_live_reaction_eligibility(factory, action):
    post = owner_post(factory)
    with factory() as db:
        canonical_feed_like(db, post, f"bulk-{action}", action=action)
    assert read_all(factory).marked_count == 1
    with factory() as db:
        row = db.scalar(select(models.Notification).where(models.Notification.world_id == WORLD))
        assert row.notification_type == action and row.read_at is not None and row.handled_at is None
        assert all(row.read_at is None for row in db.scalars(select(models.Notification).where(models.Notification.world_id.is_(None))))


def test_bulk_sql_work_scales_without_rescanning_every_post_per_descendant(factory):
    engine, instructions = factory.kw["bind"], [0]
    def progress():
        instructions[0] += 1000
        return 0
    def on_checkout(connection, *_):
        connection.set_progress_handler(progress, 1000)
    event.listen(engine, "checkout", on_checkout)
    try:
        seed_many(factory, 100, "scale-small")
        instructions[0] = 0
        assert read_all(factory).marked_count == 100
        small = instructions[0]
        seed_many(factory, 900, "scale-large")
        instructions[0] = 0
        assert read_all(factory).marked_count == 900
        # Ten times the visible rows must not cause quadratic interpreter work.
        assert small > 0 and instructions[0] < small * 25
    finally:
        event.remove(engine, "checkout", on_checkout)
        with engine.connect() as connection:
            connection.connection.driver_connection.set_progress_handler(None, 0)


@pytest.mark.parametrize("reason", ["hidden-source", "deleted-root", "blocked", "unsupported", "legacy"])
def test_bulk_uses_the_same_list_and_count_visibility(factory, reason):
    root = seed_many(factory, 1)
    with factory() as db:
        row = db.scalar(select(models.Notification))
        if reason == "hidden-source":
            db.get(models.Post, row.source_post_id).report_hidden_at = datetime.now(UTC)
        elif reason == "deleted-root":
            db.get(models.Post, root).deleted_at = datetime.now(UTC)
        elif reason == "blocked":
            db.add(models.WorldCharacterBlock(id="bulk-block", world_id=WORLD, blocker_world_character_id=ME, blocked_world_character_id=ACTOR))
        elif reason == "unsupported":
            row.notification_type = "internal-only"
        else:
            row.world_id = row.recipient_world_character_id = row.actor_world_character_id = None
        db.commit()
        assert service(db).page(world_id=WORLD, user_id=USER).items == []
        assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 0
    assert read_all(factory).marked_count == 0
    with factory() as db:
        assert db.scalar(select(models.Notification)).read_at is None


def test_bulk_rolls_back_after_update_and_two_writers_keep_first_read(factory, monkeypatch):
    from app.domains.social.repository import world_notifications as repository
    seed_many(factory, 41)
    original = repository.mark_all_read
    def fail_after_update(*args):
        original(*args)
        raise RuntimeError("controlled_bulk_rollback")
    with monkeypatch.context() as patch:
        patch.setattr(repository, "mark_all_read", fail_after_update)
        with pytest.raises(RuntimeError, match="controlled_bulk_rollback"):
            read_all(factory)
    with factory() as db:
        assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 41
    gate = Barrier(2)
    def command():
        gate.wait(timeout=5)
        return read_all(factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: command(), range(2)))
    assert sorted(row.marked_count for row in results) == [0, 41]
    first_time = next(row.read_at for row in results if row.marked_count)
    with factory() as db:
        timestamps = list(db.scalars(select(models.Notification.read_at)))
        assert all(value.replace(tzinfo=UTC) == first_time for value in timestamps)


def test_bulk_real_http_rejects_csrf_bad_body_scope_and_busy_and_keeps_later_delivery(factory, monkeypatch):
    from social.test_l4_social_write_uow import _user
    from app.domains.worlds.models_deletion import WorldDeletionRequest
    root = seed_many(factory, 41)
    with factory() as db:
        db.add(_user("other-user"))
        db.commit()
    app = application(factory)
    body = {"recipient_world_character_id": ME}
    base = f"/api/v1/worlds/{WORLD}/notifications"
    real_runner = http.run_sqlite_session_immediate
    monkeypatch.setattr(http, "run_sqlite_session_immediate", lambda db, operation: real_runner(db, operation,
        retry_policy=SqliteRetryPolicy(maximum_elapsed_seconds=0.03)))
    with TestClient(app, base_url="http://127.0.0.1:3000", headers={"Origin": "http://127.0.0.1:3000"}) as client:
        assert client.get(base).json()["unread_count"] == 41
        assert client.post(base + "/read-all", json={**body, "notification_ids": [1]}).status_code == 422
        assert client.post(base + "/read-all", json={"recipient_world_character_id": 7}).status_code == 422
        assert client.post(base + "/read-all", json={"recipient_world_character_id": "wrong-profile"}).status_code == 409
        assert client.post(base + "/read-all", json=body, headers={"Origin": "https://external.invalid"}).status_code == 403
        with factory.kw["bind"].connect() as blocker:
            blocker.exec_driver_sql("BEGIN IMMEDIATE")
            busy = client.post(base + "/read-all", json=body)
            assert busy.status_code == 503 and busy.json()["detail"] == "sqlite_busy_retry_exhausted"
            assert client.get(base).json()["unread_count"] == 41
            blocker.rollback()
        response = client.post(base + "/read-all", json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["marked_count"] == 41 and result["unread_count"] == 0 and result["read_at"].endswith("Z")
        assert client.post(base + "/read-all", json=body).json()["marked_count"] == 0
        reply(factory, root, "post-bulk-new-arrival")
        page = client.get(base).json()
        assert page["unread_count"] == 1 and page["items"][0]["read_at"] is None
        app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(id="other-user")
        assert client.post(base + "/read-all", json=body).status_code == 404
        app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(id=USER)
        with factory() as db:
            db.add(WorldDeletionRequest(id="bulk-deleting", world_id=WORLD, owner_id=USER,
                idempotency_key="c"*64, confirmation_digest="d"*64, state="accepted"))
            db.commit()
        assert client.post(base + "/read-all", json=body).status_code == 404
    with factory() as db:
        assert db.scalar(select(func.count(models.Notification.id)).where(models.Notification.read_at.is_(None))) == 1
