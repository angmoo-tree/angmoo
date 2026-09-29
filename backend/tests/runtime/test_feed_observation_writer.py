"""Exercise the real Feed observer with file WAL, atomic receipts and replay."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import sqlite3
from threading import Event
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.models import Base
from app.exceptions import SqliteBusyRetryExhausted
from app.domains.social.models.topics import RecommendationDelivery
from app.runtime.autonomous_activity.feed import FeedLane
from model_fixture_support import models
from p7_graph_support import seed_projection_fixture


def fixture(tmp_path, *, count=1):
    path = tmp_path / "feed-observation.sqlite3"
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 0.01})
    event.listen(engine, "connect", lambda raw, _: raw.execute("PRAGMA foreign_keys=ON"))
    with engine.connect() as con:
        con.exec_driver_sql("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(engine)
    identities = []
    with Session(engine, expire_on_commit=False) as db:
        for index in range(count):
            seeded = seed_projection_fixture(db, suffix=f"feed-writer-{index}")
            stamp = datetime(2026, 9, 29, 9, 17, 16, tzinfo=UTC)
            row = RecommendationDelivery(id=f"delivery-{index}", world_id=seeded.world.id,
                world_character_id=seeded.target_world_character.id,
                cycle_key=f"v2:run-{index}:feed", state="delivered",
                post_ids=[seeded.reply_post.id], trace={"_activity_observation": "pending", "retained": "yes"},
                updated_at=stamp)
            db.add(row)
            identities.append((seeded.world.id, seeded.target_world_character.id,
                               f"run-{index}", row.id, seeded.event.id, seeded.reply_post.id))
        db.commit()
    return engine, path, identities


def lane(db, identity, events=None):
    value = FeedLane.__new__(FeedLane)
    value.ctx = SimpleNamespace(db=db, run_id=identity[2])
    value.actor = SimpleNamespace(id=identity[1], world_id=identity[0])
    value.tracker = SimpleNamespace(_notify=lambda kind, facts: events.append((kind, facts))) if events is not None else None
    return value


def assert_settled(engine, identity):
    with Session(engine) as db:
        row = db.get(RecommendationDelivery, identity[3])
        assert row.trace["_activity_observation"] == "settled"
        assert row.trace["_activity_observation_results"][identity[5]] == {"status": "observed"}
        assert row.trace["retained"] == "yes"
        assert row.updated_at == datetime(2026, 9, 29, 9, 17, 16)
        assert db.scalar(select(func.count(models.RelationshipStateChange.id)).where(
            models.RelationshipStateChange.actor_world_character_id == identity[1],
            models.RelationshipStateChange.social_event_id == identity[4])) == 1
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id)).where(
            models.GraphProjectionOutbox.relationship_state_id.in_(select(models.RelationshipState.id).where(
                models.RelationshipState.actor_world_character_id == identity[1])),
            models.GraphProjectionOutbox.payload_version == "relationship-observation-v1")) == 1


def test_normal_observer_settles_and_replay_preserves_delivery(tmp_path):
    engine, _, (identity,) = fixture(tmp_path)
    with Session(engine) as db:
        actor = db.get(models.WorldCharacter, identity[1])
        actor.local_profile = {"flushed_owner_work": True}
        db.flush()
        adapter = lane(db, identity)
        adapter.observe_delivered()
        adapter.observe_delivered()
        adapter.reconcile_deliveries()
    assert_settled(engine, identity)
    with Session(engine) as db:
        assert db.get(models.WorldCharacter, identity[1]).local_profile == {"flushed_owner_work": True}
    engine.dispose()


def test_short_lock_retries_and_long_lock_remains_pending_until_recovery(tmp_path):
    engine, path, (identity,) = fixture(tmp_path)
    lock = sqlite3.connect(path, timeout=0.01)
    lock.execute("BEGIN IMMEDIATE")
    events = []
    busy = Event()
    def observe():
        with Session(engine) as db:
            adapter = lane(db, identity, events)
            def notify(kind, facts):
                events.append((kind, facts))
                if facts["result"] == "busy":
                    busy.set()
            adapter.tracker._notify = notify
            adapter.observe_delivered()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(observe)
            assert busy.wait(timeout=5)
            lock.rollback()
            future.result(timeout=5)
    finally:
        lock.close()
    assert_settled(engine, identity)
    assert any(facts["result"] == "busy" for _, facts in events)
    assert all(facts["sqlite_primary_code"] == 5 for _, facts in events if facts["result"] == "busy")
    assert all("business_key_hash" in facts and "post_id" not in facts for _, facts in events)
    assert events[-1][1]["result"] == "committed"
    engine.dispose()

    other = tmp_path / "long"
    other.mkdir()
    engine, path, (identity,) = fixture(other)
    lock = sqlite3.connect(path, timeout=0.01)
    lock.execute("BEGIN IMMEDIATE")
    try:
        with Session(engine) as db, pytest.raises(SqliteBusyRetryExhausted):
            lane(db, identity).observe_delivered()
    finally:
        lock.rollback()
        lock.close()
    with Session(engine) as db:
        assert db.get(RecommendationDelivery, identity[3]).trace["_activity_observation"] == "pending"
        lane(db, identity).reconcile_deliveries()
    assert_settled(engine, identity)
    engine.dispose()


@pytest.mark.parametrize("failure", ["program", "io", "locked"])
def test_second_source_failure_rolls_back_first_receipt_and_settlement(tmp_path, monkeypatch, failure):
    from app.runtime.social import observations
    engine, _, (identity,) = fixture(tmp_path)
    with Session(engine) as db:
        seeded = seed_projection_fixture(db, suffix="feed-second-source")
        row = db.get(RecommendationDelivery, identity[3])
        row.post_ids = [identity[5], seeded.reply_post.id]
        second = seeded.reply_post.id
        db.commit()
    original = observations.observe_source
    failures = []
    def fail(db, **kwargs):
        if kwargs["source_post_id"] == second:
            failures.append(failure)
            if failure != "program":
                from sqlalchemy.exc import OperationalError
                native = sqlite3.OperationalError("synthetic-storage-failure")
                native.sqlite_errorcode = sqlite3.SQLITE_IOERR if failure == "io" else sqlite3.SQLITE_LOCKED
                native.sqlite_errorname = "SQLITE_IOERR" if failure == "io" else "SQLITE_LOCKED"
                raise OperationalError("synthetic statement", {}, native)
            raise RuntimeError("synthetic-storage-failure")
        return original(db, **kwargs)
    monkeypatch.setattr(observations, "observe_source", fail)
    events = []
    from sqlalchemy.exc import OperationalError
    with Session(engine) as db, pytest.raises(RuntimeError if failure == "program" else OperationalError, match="synthetic-storage-failure"):
        lane(db, identity, events).observe_delivered()
    assert failures == [failure]  # No BUSY retry hides I/O, LOCKED or programming errors.
    assert events == []
    with Session(engine) as db:
        assert db.get(RecommendationDelivery, identity[3]).trace["_activity_observation"] == "pending"
        assert db.scalar(select(func.count(models.RelationshipStateChange.id)).where(
            models.RelationshipStateChange.actor_world_character_id == identity[1])) == 0
    engine.dispose()


def test_unavailable_source_records_reason_without_aborting_valid_observations(tmp_path):
    engine, _, (identity,) = fixture(tmp_path)
    with Session(engine) as db:
        row = db.get(RecommendationDelivery, identity[3])
        row.post_ids = ["deleted-source", identity[5]]
        row.updated_at = datetime(2026, 9, 29, 9, 17, 16, tzinfo=UTC)
        db.commit()
        lane(db, identity).observe_delivered()
        assert db.get(RecommendationDelivery, identity[3]).trace["_activity_observation_results"]["deleted-source"]["status"] == "not_applied"
    assert_settled(engine, identity)
    engine.dispose()


def test_three_sessions_observe_each_delivery_once(tmp_path):
    engine, _, identities = fixture(tmp_path, count=3)
    def observe(identity):
        with Session(engine) as db:
            lane(db, identity).observe_delivered()
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(observe, identities))
        list(pool.map(observe, [identities[0]] * 3))
    for identity in identities:
        observe(identity)
        assert_settled(engine, identity)
    engine.dispose()


def test_settled_replay_still_rejects_corrupt_outbox(tmp_path):
    from app.domains.relationships.exceptions import ObservationOutboxIntegrityError
    engine, _, (identity,) = fixture(tmp_path)
    with Session(engine) as db:
        lane(db, identity).observe_delivered()
        row = db.scalar(select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.payload_version == "relationship-observation-v1"))
        row.payload = {**row.payload, "target_world_character_id": "corrupt-target"}
        db.commit()
        with pytest.raises(ObservationOutboxIntegrityError):
            lane(db, identity).observe_delivered()
    assert_settled(engine, identity)
    engine.dispose()


def test_pending_scan_stops_after_first_exhausted_writer(tmp_path):
    engine, path, (identity,) = fixture(tmp_path)
    with Session(engine) as db:
        for index in range(1, 4):
            db.add(RecommendationDelivery(id=f"pending-{index}", world_id=identity[0],
                world_character_id=identity[1], cycle_key=f"old-cycle-{index}", state="delivered",
                post_ids=[identity[5]], trace={"_activity_observation": "pending"}))
        db.commit()
    lock = sqlite3.connect(path, timeout=0.01)
    lock.execute("BEGIN IMMEDIATE")
    events = []
    try:
        with Session(engine) as db, pytest.raises(SqliteBusyRetryExhausted):
            lane(db, identity, events).reconcile_deliveries()
    finally:
        lock.rollback()
        lock.close()
    assert sum(facts["result"] == "exhausted" for _, facts in events) == 1
    assert len({facts["business_key_hash"] for _, facts in events}) == 1
    with Session(engine) as db:
        assert all(row.trace["_activity_observation"] == "pending" for row in db.scalars(select(RecommendationDelivery)))
        lane(db, identity).reconcile_deliveries()
        assert all(row.trace["_activity_observation"] == "settled" for row in db.scalars(select(RecommendationDelivery)))
    assert_settled(engine, identity)
    engine.dispose()
