from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from model_fixture_support import models  # Register complete current metadata before partial DDL.
from app.core.unit_of_work import deferred_commits
from app.domains.social.constants import DELETED_CHARACTER_NAME
from app.domains.social.exceptions import CharacterOwnershipError, FollowSelfError, ProfileNotFoundError
from app.domains.social.schemas.community import FollowCreate
from app.domains.social.service import profiles


@pytest.fixture
def profile_session():
    engine = create_engine("sqlite://")
    for model in (models.User, models.Character, models.Post, models.PostLike, models.ProfileFollow, models.Notification):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = models.User(id="owner", email="owner@example.invalid", display_name="Owner", display_name_normalized="owner")
        other = models.User(id="other", email="other@example.invalid", display_name="Other", display_name_normalized="other")
        actor = models.Character(id="actor", owner_id=owner.id, name="Actor", handle="actor", persona_summary="synthetic")
        target = models.Character(id="target", owner_id=other.id, name="Target", handle="target", persona_summary="synthetic")
        db.add_all([owner, other, actor, target])
        db.commit()
        yield db, owner, actor, target
    engine.dispose()


def test_follow_workflow_deduplicates_notification_and_retains_caller_transaction(profile_session):
    db, owner, actor, target = profile_session
    commits = []
    event.listen(db, "before_commit", lambda *args: commits.append("commit"))
    data = FollowCreate(target_type="character", target_id=target.id)
    with deferred_commits():
        first = profiles.follow_profile(db, owner, data)
        second = profiles.follow_profile(db, owner, data)
        assert first == second
        assert first.follower.id == owner.id and first.target.id == target.id
        assert profiles.get_follow_status(db, owner, data).following
        assert db.scalar(select(func.count(models.ProfileFollow.id))) == 1
        assert db.scalar(select(func.count(models.Notification.id))) == 1
        notice = db.scalar(select(models.Notification))
        assert notice.recipient_character_id == target.id
        assert notice.actor_user_id == owner.id
        assert notice.notification_type == "follow"
        assert commits == []
        profiles.unfollow_profile(db, owner, data)
        assert not profiles.get_follow_status(db, owner, data).following
        assert commits == []
    db.rollback()
    assert db.scalar(select(func.count(models.ProfileFollow.id))) == 0
    assert db.scalar(select(func.count(models.Notification.id))) == 0


def test_profile_workflow_preserves_fail_closed_order_and_deleted_display(profile_session):
    db, owner, actor, target = profile_session
    with pytest.raises(CharacterOwnershipError):
        profiles.follow_profile(db, owner, FollowCreate(follower_character_id=target.id, target_type="character", target_id=actor.id))
    with pytest.raises(FollowSelfError):
        profiles.follow_profile(db, owner, FollowCreate(follower_character_id=actor.id, target_type="character", target_id=actor.id))
    with pytest.raises(ProfileNotFoundError):
        profiles.get_user_profile(db, "missing")
    assert db.scalar(select(func.count(models.ProfileFollow.id))) == 0
    assert db.scalar(select(func.count(models.Notification.id))) == 0
    target.deleted_at = datetime(2026, 9, 5, tzinfo=UTC)
    db.commit()
    result = profiles.get_character_profile(db, target.id)
    assert result.profile.id == target.id
    assert result.profile.display_name == DELETED_CHARACTER_NAME
    assert result.profile.handle is None
    assert result.profile.avatar_url is None and result.profile.banner_url is None
    with pytest.raises(ProfileNotFoundError):
        profiles.follow_profile(db, owner, FollowCreate(target_type="character", target_id=target.id))
    assert db.scalar(select(func.count(models.ProfileFollow.id))) == 0
