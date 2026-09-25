"""Committed Feed claims can be reclaimed after their lease expires."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.models import Base
from app.domains.social.constants import OBSERVATION_LEASE
from app.domains.social.contracts.search_state import SocialSearchState
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.social.models.posts import Post
from app.domains.social.service.world_feed import claim_feed_observations, renew_owned_feed_claims
from app.runtime.social.world_feed_search import (
    load_ready_search_profile,
    search_world_feed_candidates,
)
from social.test_world_feed_search import (
    _add_world_character,
    _engine,
    _post,
    _search_index,
    _seed_actor,
)


NOW = datetime(2026, 8, 11, 7, 0, tzinfo=UTC)


def test_same_token_renewal_after_expiry_never_steals_replaced_owner():
    engine, actor_id, candidates, observation_id, token = _claimed_candidate()
    with Session(engine) as db:
        renew_owned_feed_claims(db, claim_tokens={observation_id: token}, run_id="previous-run", now=NOW)
        db.commit()
        assert db.get(WorldCharacterFeedObservation, observation_id).claim_token == token
        with pytest.raises(ValueError, match="feed_claim_changed"):
            renew_owned_feed_claims(db, claim_tokens={observation_id: token}, run_id="other-run", now=NOW)
        db.rollback()
        replacement = _claim(db, actor_id, candidates, now=NOW + OBSERVATION_LEASE + timedelta(seconds=1), run_id="replacement")
        assert replacement.observations
        db.commit()
        with pytest.raises(ValueError, match="feed_claim_changed"):
            renew_owned_feed_claims(db, claim_tokens={observation_id: token}, run_id="previous-run", now=NOW + timedelta(days=1))


def _claimed_candidate(engine=None):
    engine = engine or _engine()
    with Session(engine) as db:
        world, _actor_user, _actor, actor_wc = _seed_actor(db)
        _author_user, author, author_wc = _add_world_character(
            db, world=world, suffix="reclaim-author"
        )
        post = _post(
            db,
            suffix="reclaim",
            author=author,
            world_character=author_wc,
            title="Alchemy club",
            body="Potion research",
            topic_signature="alchemy",
            created_at=NOW - timedelta(hours=2),
        )
        actor_id, post_id = actor_wc.id, post.id
        db.commit()

        profile = load_ready_search_profile(db, world_character_id=actor_id)
        search = search_world_feed_candidates(
            db,
            profile=profile,
            keywords=("alchemy", "library"),
            allowed_policy_actions=("reply", "like"),
            now=NOW,
            search_index=_search_index(db),
            search_state=SocialSearchState.READY,
        )
        assert [candidate.post_id for candidate in search.candidates] == [post_id]
        original = claim_feed_observations(
            db,
            profile=profile,
            candidates=search.candidates,
            cycle_key="previous-cycle",
            run_id="previous-run",
            now=NOW - timedelta(hours=1),
        )
        assert len(original.observations) == 1
        observation_id = original.observations[0].id
        previous_token = original.observations[0].claim_token
        db.commit()
    return engine, actor_id, search.candidates, observation_id, previous_token


def _claim(db, actor_id, candidates, *, now=NOW, run_id="new-run"):
    profile = load_ready_search_profile(db, world_character_id=actor_id)
    return claim_feed_observations(
        db,
        profile=profile,
        candidates=candidates,
        cycle_key=f"cycle-{run_id}",
        run_id=run_id,
        now=now,
    )


def test_expired_committed_feed_claim_is_reclaimed_after_sqlite_reload() -> None:
    engine, actor_id, candidates, observation_id, previous_token = _claimed_candidate()

    with Session(engine) as db:
        loaded = db.get(WorldCharacterFeedObservation, observation_id)
        assert loaded is not None
        assert loaded.lease_expires_at.tzinfo is None
        reclaimed = _claim(db, actor_id, candidates)
        assert reclaimed.claim_conflict_count == 0
        assert len(reclaimed.observations) == 1
        assert reclaimed.observations[0] is loaded
        assert loaded.id == observation_id
        assert loaded.claim_token != previous_token
        assert loaded.run_id == "new-run"
        assert loaded.cycle_key == "cycle-new-run"
        assert loaded.lease_expires_at == (NOW + OBSERVATION_LEASE).replace(tzinfo=None)
        db.commit()

    with Session(engine) as db:
        saved = db.get(WorldCharacterFeedObservation, observation_id)
        assert saved is not None
        assert saved.run_id == "new-run"
        assert saved.claim_token != previous_token
        assert saved.lease_expires_at == (NOW + OBSERVATION_LEASE).replace(tzinfo=None)


def test_claim_state_and_expiry_boundary_preserve_existing_policy() -> None:
    engine, actor_id, candidates, observation_id, _ = _claimed_candidate()
    cases = (
        ("claimed", timedelta(seconds=1), False),
        ("claimed", timedelta(0), True),
        ("claimed", timedelta(seconds=-1), True),
        ("observed", timedelta(seconds=-1), False),
        ("retryable_failed", timedelta(seconds=1), True),
    )
    for index, (status, offset, should_claim) in enumerate(cases):
        with Session(engine) as db:
            row = db.get(WorldCharacterFeedObservation, observation_id)
            row.status = status
            row.claim_token = f"previous-token-{index}"
            row.cycle_key = "previous-cycle"
            row.run_id = "previous-run"
            row.lease_expires_at = NOW + offset
            row.observed_at = NOW if status == "observed" else None
            db.commit()

        with Session(engine) as db:
            result = _claim(db, actor_id, candidates, run_id=f"run-{index}")
            assert result.claim_conflict_count == (0 if should_claim else 1)
            assert len(result.observations) == int(should_claim)
            assert len(result.candidates) == int(should_claim)
            db.commit()

        with Session(engine) as db:
            saved = db.get(WorldCharacterFeedObservation, observation_id)
            assert saved.status == ("claimed" if should_claim else status)
            if should_claim:
                assert saved.claim_token != f"previous-token-{index}"
            else:
                assert saved.claim_token == f"previous-token-{index}"
            assert saved.run_id == (f"run-{index}" if should_claim else "previous-run")
            if not should_claim:
                assert saved.lease_expires_at == (NOW + offset).replace(tzinfo=None)
                assert saved.observed_at == (NOW.replace(tzinfo=None) if status == "observed" else None)


def test_utc_offset_and_naive_utc_inputs_reclaim_same_expired_row() -> None:
    engine, actor_id, candidates, observation_id, previous_token = _claimed_candidate()
    for now in (NOW, NOW.astimezone(timezone(timedelta(hours=9))), NOW.replace(tzinfo=None)):
        with Session(engine) as db:
            result = _claim(db, actor_id, candidates, now=now)
            assert result.claim_conflict_count == 0
            assert result.observations[0].claim_token != previous_token
            db.rollback()
        with Session(engine) as db:
            saved = db.get(WorldCharacterFeedObservation, observation_id)
            assert saved.claim_token == previous_token
            assert saved.run_id == "previous-run"
            assert saved.lease_expires_at == (NOW - timedelta(hours=1) + OBSERVATION_LEASE).replace(tzinfo=None)


def test_mixed_session_datetime_representations_do_not_change_unrelated_claim() -> None:
    engine, actor_id, candidates, observation_id, _ = _claimed_candidate()
    with Session(engine) as db:
        loaded = db.get(WorldCharacterFeedObservation, observation_id)
        post = db.get(Post, candidates[0].post_id)
        unrelated = WorldCharacterFeedObservation(
            id="feed-observation-unrelated",
            world_id=post.world_id,
            observer_world_character_id=post.author_world_character_id,
            post_id=post.id,
            status="claimed",
            claim_token="unrelated-token",
            lease_expires_at=NOW + timedelta(minutes=1),
            cycle_key="unrelated-cycle",
            run_id="unrelated-run",
            matched_keywords=[],
            matched_fields=[],
            rank_score=0,
            post_created_at=post.created_at,
            claimed_at=NOW,
        )
        db.add(unrelated)
        db.flush()
        assert loaded.lease_expires_at.tzinfo is None
        assert unrelated.lease_expires_at.tzinfo is not None
        result = _claim(db, actor_id, candidates)
        assert result.observations == (loaded,)
        assert unrelated.claim_token == "unrelated-token"
        assert unrelated.run_id == "unrelated-run"


def test_sql_write_failure_propagates_without_committing_existing_claim() -> None:
    engine, actor_id, candidates, observation_id, previous_token = _claimed_candidate()

    def reject_update(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("UPDATE WORLD_CHARACTER_FEED_OBSERVATIONS"):
            raise RuntimeError("synthetic claim write failure")

    event.listen(engine, "before_cursor_execute", reject_update)
    try:
        with Session(engine) as db:
            with pytest.raises(RuntimeError, match="synthetic claim write failure"):
                _claim(db, actor_id, candidates)
            db.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", reject_update)

    with Session(engine) as db:
        saved = db.get(WorldCharacterFeedObservation, observation_id)
        assert saved.claim_token == previous_token
        assert saved.run_id == "previous-run"


def test_stale_reader_loses_conditional_update_to_other_connection(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'feed.sqlite'}", poolclass=NullPool)
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    engine, actor_id, candidates, observation_id, _ = _claimed_candidate(engine)
    with Session(engine) as stale, Session(engine) as winner:
        old_row = stale.get(WorldCharacterFeedObservation, observation_id)
        assert old_row.run_id == "previous-run"
        won = _claim(winner, actor_id, candidates, run_id="winner")
        assert len(won.observations) == 1
        winning_token = won.observations[0].claim_token
        winner.commit()
        lost = _claim(stale, actor_id, candidates, run_id="loser")
        assert lost.observations == ()
        assert lost.claim_conflict_count == 1
        stale.rollback()
    with Session(engine) as db:
        saved = db.get(WorldCharacterFeedObservation, observation_id)
        assert saved.run_id == "winner"
        assert saved.claim_token == winning_token
    engine.dispose()


def test_only_one_file_sqlite_contender_acquires_expired_claim(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'feed-race.sqlite'}",
        poolclass=NullPool,
        connect_args={"timeout": 5},
    )
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    engine, actor_id, candidates, observation_id, _ = _claimed_candidate(engine)
    barrier = Barrier(2)

    def contend(name):
        with Session(engine) as db:
            db.get(WorldCharacterFeedObservation, observation_id)
            barrier.wait(timeout=10)
            try:
                result = _claim(db, actor_id, candidates, run_id=name)
                db.commit()
                return ("acquired" if result.observations else "conflict", name)
            except OperationalError as exc:
                db.rollback()
                assert "locked" in str(exc).lower()
                return ("locked", name)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(contend, ("contender-a", "contender-b")))
    assert [outcome for outcome, _ in outcomes].count("acquired") == 1
    assert [outcome for outcome, _ in outcomes].count("conflict") + [outcome for outcome, _ in outcomes].count("locked") == 1
    winner = next(name for outcome, name in outcomes if outcome == "acquired")
    with Session(engine) as db:
        saved = db.get(WorldCharacterFeedObservation, observation_id)
        assert saved.run_id == winner
        assert db.scalar(select(func.count(WorldCharacterFeedObservation.id))) == 1
    engine.dispose()
