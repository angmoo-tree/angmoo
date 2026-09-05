from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.domains.routines import public as routines
from app.services import activity_runtime
from routines.test_daily_activity_runtime import _add_social_event, _prepare, _seed, _utc


@pytest.mark.parametrize(
    "owner_controlled", [False, True], ids=["autonomous", "owner-controlled"]
)
def test_guarded_recovery_uses_consumption_owner_and_preserves_admission(
    tmp_path, owner_controlled: bool
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'guarded-recovery.sqlite3'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    now = _utc(datetime(2026, 8, 9, 1, 0))
    with Session(engine, expire_on_commit=False) as db:
        world, fixture, other = _seed(db, two_characters=True)
        assert other is not None
        _add_social_event(
            db,
            event_id="guarded-expired-event",
            world_id=world.id,
            actor_world_character_id=other.world_character.id,
            target_world_character_id=fixture.world_character.id,
            occurred_at=now - timedelta(minutes=1),
        )
        db.commit()
        plan = _prepare(db, fixture, now=now)
        episode = plan.items[0].episode
        assert episode is not None
        beat = activity_runtime.claim_activity_beat(
            db,
            episode_id=episode.id,
            scheduled_for=now,
            trigger_kind="comment_influenced",
            idempotency_key="guarded-beat",
            claim_run_id="guarded-run",
            claim_expires_at=now + timedelta(hours=1),
            source_event_ids=["guarded-expired-event"],
            now=now,
        )
        consumption = activity_runtime.claim_event_consumption(
            db,
            world_id=world.id,
            consumer_world_character_id=fixture.world_character.id,
            source_social_event_id="guarded-expired-event",
            target_activity_beat_id=beat.row.id,
            idempotency_key="guarded-consumption",
            claim_run_id="guarded-run",
            claim_expires_at=now + timedelta(minutes=5),
            now=now,
        )
        beat_id = beat.row.id
        consumption_id = consumption.row.id
        previous_version = consumption.row.version
        if owner_controlled:
            fixture.world_character.control_mode = "owner_controlled"
            fixture.world_character.owner_user_id = fixture.user.id
            db.commit()

    with Session(engine, expire_on_commit=False) as restarted:
        def recover():
            return routines.recover_expired_claims(
                restarted, clock=routines.FrozenClock(now + timedelta(minutes=6))
            )

        if owner_controlled:
            with pytest.raises(
                routines.ActivityRuntimeValidationError,
                match="owner_controlled_automation_disabled",
            ):
                recover()
            restarted.rollback()
        else:
            assert recover() == routines.RecoveryCounts(beats=0, consumptions=1)
            assert recover() == routines.RecoveryCounts(beats=0, consumptions=0)

    with Session(engine) as observer:
        saved = observer.get(models.ActivityEventConsumption, consumption_id)
        saved_beat = observer.get(models.ActivityBeat, beat_id)
        assert saved is not None
        assert saved_beat is not None
        assert saved.status == ("claimed" if owner_controlled else "released")
        assert saved.version == previous_version + (0 if owner_controlled else 1)
        assert saved.claim_run_id == ("guarded-run" if owner_controlled else None)
        assert (saved.claim_expires_at is not None) is owner_controlled
        assert saved.target_activity_beat_id == (beat_id if owner_controlled else None)
        assert saved_beat.status == "claimed"
        assert saved_beat.claim_run_id == "guarded-run"
        assert observer.scalar(select(func.count(models.Post.id))) == 0
        assert observer.scalar(select(func.count(models.AgentRun.id))) == 0
        assert observer.scalar(select(func.count(models.SocialEvent.id))) == 1
    engine.dispose()
