"""File-backed WAL regression cases for relationship writer boundaries."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import sqlite3
from threading import Barrier
from time import monotonic, sleep

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.core.sqlite_concurrency import SqliteConcurrencyError, run_sqlite_session_immediate
from app.core import sqlite_concurrency
from app.domains.relationships.models.personalization import (
    RelationshipExperienceReceipt, RelationshipMetricApplication,
)
from app.domains.relationships.service.policy_activation import activate_policy
from app.domains.social.models.posts import Post
from app.domains.world_characters.schemas.activity_state import StateUpdate
from app.domains.world_characters.activity_models import CharacterActivityState
from app.domains.world_characters.service.activity_state import settle_state
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import World
from app.models import Base
from app.runtime.relationships.experience_metrics import apply_pending_metrics, post_revision
from app.runtime.relationships.social_metrics import prepare_sources, stage_sources
from app.runtime.relationships import social_metrics, experience_metrics
from model_fixture_support import models
from p7_graph_support import seed_projection_fixture


def _fixture(tmp_path, *, count=1):
    path = tmp_path / "relationship-wal.sqlite3"
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 0.01, "check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _foreign_keys(raw, _record):
        raw.execute("PRAGMA foreign_keys=ON")

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(engine)
    identities = []
    with Session(engine) as db:
        for index in range(count):
            fixture = seed_projection_fixture(db, suffix=f"wal-{index}")
            activate_policy(db, world_id=fixture.world.id,
                now=datetime.now(UTC) - timedelta(days=1))
            db.commit()
            identities.append((fixture.world.id, fixture.actor_world_character.id,
                               fixture.target_world_character.id, fixture.root_post.id))
    return engine, path, identities


def _stage(engine, identity, *, decision="inbox", observer=None):
    world_id, actor_id, target_id, post_id = identity
    with Session(engine) as db:
        actor = db.get(WorldCharacter, actor_id)
        manifest = prepare_sources(db, actor=actor, post_ids=[post_id])
        raw = [{"target_ref": target_id, "affinity": "increase", "trust": "keep",
                "tension": "decrease", "new_evidence_refs": [post_id]}]
        return stage_sources(db, actor=actor, manifest=manifest, raw=raw,
            decision_key=decision, now=datetime.now(UTC), write_observer=observer)


def test_three_independent_sessions_stage_once_each_and_replay_is_idempotent(tmp_path):
    engine, _, identities = _fixture(tmp_path, count=3)
    barrier = Barrier(3)

    def worker(identity):
        barrier.wait()
        return _stage(engine, identity)

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(pool.map(worker, identities))
    for identity in identities:
        _stage(engine, identity, decision="feed-replay")
        with Session(engine) as db:
            apply_pending_metrics(db, world_id=identity[0])
            apply_pending_metrics(db, world_id=identity[0])
            receipts = list(db.scalars(select(RelationshipExperienceReceipt).where(
                RelationshipExperienceReceipt.world_id == identity[0])))
            applications = list(db.scalars(select(RelationshipMetricApplication).join(
                RelationshipExperienceReceipt,
                RelationshipExperienceReceipt.id == RelationshipMetricApplication.experience_id).where(
                    RelationshipExperienceReceipt.world_id == identity[0])))
            assert len(receipts) == len(applications) == 1
            assert applications[0].status == "applied"
    engine.dispose()


def test_observed_post_remains_state_evidence_when_relationship_manifest_is_empty(tmp_path):
    engine, _, (identity,) = _fixture(tmp_path)
    world_id, actor_id, _, post_id = identity
    observed_calls = []
    with Session(engine) as db:
        actor = db.get(WorldCharacter, actor_id)
        post = db.get(Post, post_id)
        revision = post_revision(post)
        observed = stage_sources(db, actor=actor, manifest=[], raw=None,
            decision_key="no-relationship-manifest", now=datetime.now(UTC),
            observed_post_ids={post_id: revision}, observation_lane="feed",
            observe_post=observed_calls.append)
        assert observed == (post_id,)
        assert observed_calls == [post_id]
        assert db.scalar(select(RelationshipExperienceReceipt.id)) is None
    engine.dispose()


def test_changed_observed_post_is_not_retained_as_state_evidence(tmp_path):
    engine, _, (identity,) = _fixture(tmp_path)
    actor_id, post_id = identity[1], identity[3]
    with Session(engine) as db:
        actor = db.get(WorldCharacter, actor_id)
        observed = stage_sources(db, actor=actor, manifest=[], raw=None,
            decision_key="changed-observation", now=datetime.now(UTC),
            observed_post_ids={post_id: "old-revision"}, observation_lane="feed",
            observe_post=lambda _ref: pytest.fail("stale post observed"))
        assert observed == ()
    engine.dispose()


def test_short_writer_conflict_retries_complete_unit_and_long_conflict_exhausts(tmp_path):
    engine, path, (identity,) = _fixture(tmp_path)
    with engine.connect() as connection:
        original_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
    events = []
    lock = sqlite3.connect(path, timeout=0.01)
    lock.execute("BEGIN IMMEDIATE")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_stage, engine, identity, observer=events.append)
            sleep(0.075)
            lock.rollback()
            assert future.result(timeout=5) == (identity[3],)
    finally:
        lock.close()
    assert events[-1]["result"] == "committed"
    with Session(engine) as db:
        assert db.scalar(select(RelationshipExperienceReceipt.id)) is not None
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == original_timeout

    # A second fixture avoids replay's existing receipt short-circuit.
    engine.dispose()
    other = tmp_path / "other"
    other.mkdir()
    engine, path, (identity,) = _fixture(other)
    lock = sqlite3.connect(path, timeout=0.01)
    lock.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(Exception) as failure:
            _stage(engine, identity)
        assert type(failure.value).__name__ == "SqliteBusyRetryExhausted"
        assert failure.value.sqlite_errorcode is not None
        assert failure.value.__cause__ is not None
        with Session(engine) as db:
            assert db.scalar(select(RelationshipExperienceReceipt.id)) is None
    finally:
        lock.rollback()
        lock.close()
    assert _stage(engine, identity) == (identity[3],)
    engine.dispose()


def test_busy_writer_blocks_async_loop_only_within_bounded_retry_window(tmp_path):
    engine, path, (identity,) = _fixture(tmp_path)
    lock = sqlite3.connect(path, timeout=0.01)
    lock.execute("BEGIN IMMEDIATE")
    try:
        async def measure():
            async def heartbeat():
                started = monotonic()
                await asyncio.sleep(0.01)
                return monotonic() - started - 0.01
            pulse = asyncio.create_task(heartbeat())
            await asyncio.sleep(0)
            started = monotonic()
            with pytest.raises(sqlite_concurrency.SqliteBusyRetryExhausted):
                _stage(engine, identity)
            elapsed = monotonic() - started
            lag = await pulse
            return elapsed, lag
        elapsed, lag = asyncio.run(measure())
        # This synchronous Session currently blocks the loop for the bounded
        # writer attempt. Keep the measured bound visible for later tuning.
        assert 0.05 <= lag <= elapsed + 0.1
        assert elapsed < 1.0
    finally:
        lock.rollback()
        lock.close()
        engine.dispose()


def test_flushed_outer_work_is_not_silently_rolled_back(tmp_path):
    engine, _, (identity,) = _fixture(tmp_path)
    with Session(engine) as db:
        world = db.get(World, identity[0])
        world.tagline = "Preserve this flushed work"
        db.flush()
        with pytest.raises(SqliteConcurrencyError, match="requires_clean_session"):
            run_sqlite_session_immediate(db, lambda: None, require_clean=True)
        db.commit()
    with Session(engine) as db:
        assert db.get(World, identity[0]).tagline == "Preserve this flushed work"
    engine.dispose()


def test_sqlite_error_codes_distinguish_busy_snapshot_from_locked_and_io(tmp_path):
    engine, _, _ = _fixture(tmp_path)
    busy_snapshot = sqlite3.OperationalError("database is locked")
    busy_snapshot.sqlite_errorcode = sqlite3.SQLITE_BUSY_SNAPSHOT
    busy_snapshot.sqlite_errorname = "SQLITE_BUSY_SNAPSHOT"
    locked = sqlite3.OperationalError("database is locked")
    locked.sqlite_errorcode = sqlite3.SQLITE_LOCKED
    locked.sqlite_errorname = "SQLITE_LOCKED"
    assert sqlite_concurrency._is_busy_error(busy_snapshot)
    assert not sqlite_concurrency._is_busy_error(locked)
    calls = []
    with Session(engine) as db:
        def fail():
            calls.append(1)
            raise locked
        with pytest.raises(sqlite3.OperationalError):
            run_sqlite_session_immediate(db, fail, require_clean=True)
    assert calls == [1]
    engine.dispose()


def test_stage_failure_rolls_back_receipt_and_application_together(tmp_path, monkeypatch):
    engine, _, (identity,) = _fixture(tmp_path)
    original = social_metrics.stage_experience

    def fail_after_staging(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic_after_receipt_and_application_flush")

    monkeypatch.setattr(social_metrics, "stage_experience", fail_after_staging)
    with pytest.raises(RuntimeError, match="synthetic_after"):
        _stage(engine, identity)
    with Session(engine) as db:
        assert db.scalar(select(RelationshipExperienceReceipt.id)) is None
        assert db.scalar(select(RelationshipMetricApplication.id)) is None
    monkeypatch.setattr(social_metrics, "stage_experience", original)
    assert _stage(engine, identity) == (identity[3],)
    engine.dispose()


def test_scope_loss_inside_writer_rejects_staging_without_receipt(tmp_path):
    engine, _, (identity,) = _fixture(tmp_path)
    world_id, actor_id, target_id, post_id = identity
    with Session(engine) as db:
        actor = db.get(WorldCharacter, actor_id)
        manifest = prepare_sources(db, actor=actor, post_ids=[post_id])
        def lost_claim():
            raise ValueError("activity_claim_lost")
        with pytest.raises(ValueError, match="activity_claim_lost"):
            stage_sources(db, actor=actor, manifest=manifest,
                raw=[{"target_ref": target_id, "new_evidence_refs": [post_id]}],
                decision_key="claim-lost", now=datetime.now(UTC), scope_validator=lost_claim)
    with Session(engine) as db:
        assert db.scalar(select(RelationshipExperienceReceipt.id).where(
            RelationshipExperienceReceipt.world_id == world_id)) is None
    engine.dispose()


def test_pending_application_failure_preserves_receipt_then_applies_once(tmp_path, monkeypatch):
    engine, _, (identity,) = _fixture(tmp_path)
    _stage(engine, identity)
    original = experience_metrics.apply_staged_experience

    def fail_before_apply(*args, **kwargs):
        raise RuntimeError("synthetic_s2_failure")

    monkeypatch.setattr(experience_metrics, "apply_staged_experience", fail_before_apply)
    with Session(engine) as db, pytest.raises(RuntimeError, match="synthetic_s2_failure"):
        apply_pending_metrics(db, world_id=identity[0])
    with Session(engine) as db:
        assert db.scalar(select(RelationshipExperienceReceipt.id)) is not None
        assert db.scalar(select(RelationshipMetricApplication.status)) == "pending"
    monkeypatch.setattr(experience_metrics, "apply_staged_experience", original)
    with Session(engine) as db:
        apply_pending_metrics(db, world_id=identity[0])
        state = db.scalar(select(models.RelationshipState).where(
            models.RelationshipState.world_id == identity[0],
            models.RelationshipState.actor_world_character_id == identity[1],
            models.RelationshipState.target_world_character_id == identity[2]))
        assert state is not None
        version = state.version
        assert db.scalar(select(RelationshipMetricApplication.status)) == "applied"
        apply_pending_metrics(db, world_id=identity[0])
        db.refresh(state)
        assert state.version == version
    engine.dispose()


def test_pending_worker_and_settlement_compete_without_double_apply(tmp_path):
    engine, _, (identity,) = _fixture(tmp_path)
    _stage(engine, identity)
    with Session(engine) as db:
        before_version = db.scalar(select(models.RelationshipState.version).where(
            models.RelationshipState.world_id == identity[0],
            models.RelationshipState.actor_world_character_id == identity[1],
            models.RelationshipState.target_world_character_id == identity[2]))
    barrier = Barrier(2)
    def apply():
        with Session(engine) as db:
            barrier.wait(timeout=5)
            return apply_pending_metrics(db, world_id=identity[0], actor_id=identity[1])
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: apply(), range(2)))
    with Session(engine) as db:
        assert db.scalar(select(RelationshipMetricApplication.status)) == "applied"
        rows = list(db.scalars(select(models.RelationshipState).where(
            models.RelationshipState.world_id == identity[0],
            models.RelationshipState.actor_world_character_id == identity[1],
            models.RelationshipState.target_world_character_id == identity[2])))
        assert len(rows) == 1
        assert rows[0].version == before_version + 1
    engine.dispose()


def test_state_settlement_immediate_replay_keeps_decision_receipt_and_cas(tmp_path):
    engine, _, (identity,) = _fixture(tmp_path)
    world_id, actor_id, _, _ = identity
    judged_at = datetime.now(UTC)
    with Session(engine) as db:
        def settle(decision_key, expected_version):
            return run_sqlite_session_immediate(db, lambda: settle_state(db,
                world_id=world_id, actor_id=actor_id, activity_id="synthetic-activity",
                decision_key=decision_key, expected_version=expected_version,
                proposal=StateUpdate(mood="curious", mood_intensity=50, state_note="Checking a fixture"),
                judged_at=judged_at, source_keys=["synthetic-evidence"],
                valid_source_keys={"synthetic-evidence"}), require_clean=True)
        assert settle("decision-1", 0) == "updated"
        assert settle("decision-1", 0) == "updated"
        assert settle("decision-2", 0) == "already_interpreted"
        assert db.scalar(select(CharacterActivityState.version)) == 1
    engine.dispose()
