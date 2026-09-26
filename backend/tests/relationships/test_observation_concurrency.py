"""Independent SQLite connections settle competing observation transactions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from model_fixture_support import models
from app.domains.world_characters.service import setup_validation as contracts
from app.domains.relationships.exceptions import ObservationOutboxIntegrityError
from app.domains.social.models.topics import RecommendationDelivery
from app.models import Base
from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.social.observations import observe_source
from p7_graph_support import seed_projection_fixture
from relationships.test_social_event_runtime import _character, _user


def _engine(path: Path):
    engine = create_engine(
        f"sqlite:///{path.as_posix()}",
        connect_args={"timeout": 0.2}, poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _add_second_observer(db: Session, world: models.World) -> str:
    owner = _user("concurrent-second")
    character = _character(owner, "concurrent-second")
    db.add_all((owner, character))
    db.flush()
    membership = models.WorldMembership(
        id="membership-concurrent-second", world_id=world.id, user_id=owner.id,
        role="member", status="active", joined_at=datetime(2026, 9, 24, tzinfo=UTC),
    )
    db.add(membership)
    db.flush()
    observer = models.WorldCharacter(
        id="world-character-concurrent-second",
        world_id=world.id, character_id=character.id,
        membership_id=membership.id, role_key="student", status="active",
        character_contract_hash=contracts.character_contract_hash(character),
        world_contract_hash=world.contract_hash,
    )
    db.add(observer)
    db.commit()
    return observer.id


@pytest.mark.parametrize("same_observer", [True, False])
def test_concurrent_observations_on_separate_sqlite_connections(
    tmp_path: Path, same_observer: bool,
) -> None:
    engine = _engine(tmp_path / "observations.sqlite3")
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="concurrent")
        other_id = _add_second_observer(db, fixture.world)
        ids = (
            fixture.target_world_character.id,
            fixture.target_world_character.id if same_observer else other_id,
        )
        world_id, event_id, post_id = (
            fixture.world.id, fixture.event.id, fixture.reply_post.id,
        )
    start = Barrier(2)

    def write(observer_id: str):
        start.wait(timeout=5)
        for attempt in range(6):
            try:
                with Session(engine, expire_on_commit=False) as db:
                    result = observe_source(
                        db, world_id=world_id,
                        observer_world_character_id=observer_id,
                        source_social_event_id=event_id, source_post_id=post_id,
                        lane="feed", observed_at=datetime(2026, 9, 24, tzinfo=UTC),
                    )
                    db.commit()
                    return result
            except (OperationalError, IntegrityError) as exc:
                detail = str(exc).lower()
                replayable_race = (
                    "locked" in detail
                    or "unique constraint failed: relationship_states.world_id" in detail
                    or "unique constraint failed: relationship_state_changes.relationship_state_id" in detail
                )
                if not replayable_race or attempt == 5:
                    raise
                # The complete caller UOW is closed before a fresh read/retry.
                time.sleep(0.02 * (attempt + 1))
        raise AssertionError("unreachable")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(write, observer_id) for observer_id in ids]
        results = [future.result(timeout=10) for future in futures]
    with Session(engine) as db:
        observation_rows = list(db.scalars(select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.payload_version == "relationship-observation-v1"
        )))
        expected = 1 if same_observer else 2
        assert len(observation_rows) == expected
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 1 + expected
        assert len({result.receipt_id for result in results}) == expected
        assert len({result.relationship_state_id for result in results}) == expected
        if same_observer:
            assert any(result.replayed for result in results)
    engine.dispose()


def test_feed_delivery_settlement_keeps_two_observer_directions(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "feed-delivery.sqlite3")
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="feed-delivery")
        second_id = _add_second_observer(db, fixture.world)
        for run_id, observer_id in (
            ("feed-first", fixture.target_world_character.id),
            ("feed-second", second_id),
        ):
            db.add(RecommendationDelivery(
                id=f"delivery-{run_id}", world_id=fixture.world.id,
                world_character_id=observer_id, cycle_key=f"v2:{run_id}:feed",
                state="delivered", post_ids=[fixture.reply_post.id], trace={},
            ))
        db.commit()

        def settle(run_id: str, observer_id: str) -> None:
            lane = FeedLane.__new__(FeedLane)
            lane.ctx = SimpleNamespace(db=db, run_id=run_id)
            lane.actor = db.get(models.WorldCharacter, observer_id)
            lane.observe_delivered()

        settle("feed-first", fixture.target_world_character.id)
        first = db.scalar(select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.payload_version == "relationship-observation-v1"
        ))
        assert first is not None
        first.status = "succeeded"
        db.commit()
        settle("feed-second", second_id)
        rows = list(db.scalars(select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.payload_version == "relationship-observation-v1"
        )))
        assert len(rows) == 2
        assert len({row.relationship_state_id for row in rows}) == 2
        assert all(row.relationship_state_id for row in rows)
        assert {row.payload["actor_world_character_id"] for row in rows} == {
            fixture.target_world_character.id, second_id,
        }

        first.payload = {**first.payload, "target_world_character_id": "wrong"}
        db.commit()
        with pytest.raises(ObservationOutboxIntegrityError):
            settle("feed-first", fixture.target_world_character.id)
        db.rollback()
    engine.dispose()
