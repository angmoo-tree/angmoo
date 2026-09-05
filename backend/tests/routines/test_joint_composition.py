from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.domains.routines.service.joint_activity import execution
from app.runtime.routines.joint_references import SqlAlchemyJointReferences
from routines.test_daily_activity_runtime import _utc
from test_activity_proposal_runtime import _post, _ready_joint_fixture, _record_post_event


@pytest.mark.parametrize("outcome", ["commit", "rollback"])
def test_opening_post_event_notification_and_participants_share_one_transaction(tmp_path, outcome):
    engine = create_engine(f"sqlite:///{tmp_path / 'joint-composition.sqlite3'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    now = _utc(datetime(2026, 8, 9, 0, 30))
    try:
        with Session(engine, expire_on_commit=False) as db:
            fixture = _ready_joint_fixture(db, now=now, prefix="joint-same-session")
            opening_at = fixture.schedule.scheduled_start_at + timedelta(minutes=5)
            joint_id = fixture.joint.id
            claim = execution.claim_opening(
                db,
                references=SqlAlchemyJointReferences(db),
                joint_activity_id=joint_id,
                claimant_world_character_id=fixture.proposer.world_character.id,
                now=opening_at,
            )
            commits = []
            event.listen(db, "after_commit", lambda _session: commits.append(True))
            post = _post(
                db,
                post_id="joint-same-session-opening",
                fixture=fixture.proposer,
                body="We began observing together.",
                created_at=opening_at,
            )
            post_event = _record_post_event(
                db,
                world_id=fixture.world.id,
                actor_world_character_id=fixture.proposer.world_character.id,
                target_world_character_id=None,
                event_type="post_published",
                source=post,
                target_post_id=None,
                root_post_id=post.id,
                occurred_at=opening_at,
                idempotency_key="joint-same-session-opening-event",
            )
            operations = []

            class ObservedReferences(SqlAlchemyJointReferences):
                def set_joint_activity_id(self, value, *, joint_activity_id):
                    assert value is post and value in db
                    assert value.opening_post_id is None
                    operations.append("joint-link")
                    super().set_joint_activity_id(value, joint_activity_id=joint_activity_id)

                def set_opening_post_id(self, value, *, opening_post_id):
                    assert value is post and value.joint_activity_id == joint_id
                    operations.append("opening-link")
                    super().set_opening_post_id(value, opening_post_id=opening_post_id)

                def record_started_event(self, **kwargs):
                    assert kwargs["joint"] is fixture.joint
                    assert kwargs["post"] is post
                    assert kwargs["post_event"] is post_event
                    operations.append("started-event")
                    return super().record_started_event(**kwargs)

                def get_world_character(self, world_character_id, *, lock_for_update=False):
                    result = super().get_world_character(
                        world_character_id, lock_for_update=lock_for_update
                    )
                    assert result in db
                    operations.append(world_character_id)
                    return result

                def ensure_started_notification(self, **kwargs):
                    assert kwargs["post_id"] == post.id
                    operations.append("notification")
                    super().ensure_started_notification(**kwargs)

            started = execution.apply_joint_post(
                db,
                references=ObservedReferences(db),
                joint_activity_id=joint_id,
                author_world_character_id=fixture.proposer.world_character.id,
                post=post,
                post_event=post_event,
                opening_claim=claim,
                now=opening_at,
            )
            assert started is not None and started in db
            assert operations == [
                "joint-link", "opening-link", "started-event",
                fixture.acceptor.world_character.id,
                fixture.proposer.world_character.id,
                "notification",
            ]
            assert commits == []
            with Session(engine) as observer:
                assert observer.get(models.Post, post.id) is None
                assert observer.get(models.JointActivity, joint_id).status == "ready"
                assert observer.scalar(select(func.count(models.Notification.id))) == 0
                assert observer.get(models.SocialEvent, started.id) is None
            started_id, post_event_id = started.id, post_event.id
            if outcome == "commit":
                db.commit()
                assert commits == [True]
            else:
                db.rollback()
                assert commits == []

        with Session(engine) as observer:
            joint = observer.get(models.JointActivity, joint_id)
            participants = list(observer.scalars(select(models.JointActivityParticipant).where(
                models.JointActivityParticipant.joint_activity_id == joint_id
            )))
            assert len(participants) == 2
            expected = "active" if outcome == "commit" else "scheduled"
            assert {row.participation_status for row in participants} == {expected}
            assert {observer.get(models.ActivityEpisode, row.linked_activity_episode_id).status for row in participants} == {"active" if outcome == "commit" else "planned"}
            assert {observer.get(models.DailyActivityPlanItem, row.linked_daily_activity_plan_item_id).status for row in participants} == {"active" if outcome == "commit" else "planned"}
            assert joint.status == ("active" if outcome == "commit" else "ready")
            assert (observer.get(models.SocialEvent, started_id) is not None) == (outcome == "commit")
            assert (observer.get(models.SocialEvent, post_event_id) is not None) == (outcome == "commit")
            assert observer.scalar(select(func.count(models.Notification.id))) == (1 if outcome == "commit" else 0)
            saved_post = observer.get(models.Post, "joint-same-session-opening")
            if outcome == "commit":
                assert saved_post.joint_activity_id == joint_id
                assert saved_post.opening_post_id == saved_post.id == joint.opening_post_id
            else:
                assert saved_post is None and joint.opening_post_id is None
    finally:
        engine.dispose()
