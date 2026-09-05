from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.domains.relationships.service import observations
from app.domains.social.contracts.observations import (
    SocialObservationCommand,
    SocialObservationError,
)
from app.runtime.relationships import observation_references
from app.runtime.social.observations import observe_source
from p7_graph_support import seed_projection_fixture, sqlite_engine


def _counts(db):
    return tuple(
        db.scalar(select(func.count(model.id)))
        for model in (
            models.SocialEvent,
            models.RelationshipState,
            models.RelationshipStateChange,
            models.GraphProjectionOutbox,
        )
    )


def test_observation_uses_same_session_sources_and_caller_rollback(monkeypatch):
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="observation-owner")
        before = _counts(db)
        calls = []
        original_scope = observation_references.validate_event_scope
        original_post = observation_references.get_post
        original_block = observation_references.write_pair_is_blocked

        def scope(session, **kwargs):
            assert session is db
            row = original_scope(session, **kwargs)
            calls.append(("scope", row, kwargs.get("lock", False)))
            return row

        def post(session, post_id):
            assert session is db
            row = original_post(session, post_id)
            calls.append(("post", row))
            return row

        def blocked(session, **kwargs):
            assert session is db
            calls.append(("block", kwargs["actor_id"], kwargs["target_id"]))
            return original_block(session, **kwargs)

        def commit_forbidden():
            raise AssertionError("observation must leave commit to its caller")

        monkeypatch.setattr(observation_references, "validate_event_scope", scope)
        monkeypatch.setattr(observation_references, "get_post", post)
        monkeypatch.setattr(observation_references, "write_pair_is_blocked", blocked)
        monkeypatch.setattr(db, "commit", commit_forbidden)
        result = observe_source(
            db,
            world_id=fixture.world.id,
            observer_world_character_id=fixture.target_world_character.id,
            source_social_event_id=fixture.event.id,
            source_post_id=None,
            lane="feed",
            observed_at=datetime(2026, 9, 6, 1, 0, tzinfo=UTC),
        )
        assert calls == [
            ("scope", fixture.target_world_character, True),
            ("post", fixture.reply_post),
            ("scope", fixture.actor_world_character, False),
            ("block", fixture.target_world_character.id, fixture.actor_world_character.id),
        ]
        assert _counts(db) == (before[0], before[1] + 1, before[2] + 1, before[3] + 1)
        observed = db.get(models.RelationshipState, result.relationship_state_id)
        assert observed.familiarity == 1
        assert (observed.affinity, observed.trust, observed.tension) == (0, 0, 0)
        assert fixture.relationship.actor_world_character_id == fixture.actor_world_character.id
        receipt_id, state_id = result.receipt_id, result.relationship_state_id
        db.rollback()
        assert _counts(db) == before
        assert db.get(models.RelationshipStateChange, receipt_id) is None
        assert db.get(models.RelationshipState, state_id) is None
        assert db.get(models.SocialEvent, fixture.event.id) is fixture.event
    engine.dispose()


@pytest.mark.parametrize(
    ("change", "reason", "reads_post"),
    [
        ("observer_left", "world_character_inactive", False),
        ("membership_left", "world_membership_inactive", False),
        ("blocked", "world_character_blocked", True),
    ],
)
def test_observation_revalidates_active_scope_and_block_before_relation_write(
    monkeypatch, change, reason, reads_post
):
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="observation-denied")
        if change == "observer_left":
            fixture.target_world_character.status = "left"
        elif change == "membership_left":
            db.get(models.WorldMembership, fixture.target_world_character.membership_id).status = "left"
        else:
            db.add(models.WorldCharacterBlock(
                id="observation-mutual-block",
                world_id=fixture.world.id,
                blocker_world_character_id=fixture.actor_world_character.id,
                blocked_world_character_id=fixture.target_world_character.id,
            ))
        db.commit()
        before = _counts(db)
        post_reads = []
        original = observation_references.get_post

        def read_post(session, post_id):
            assert session is db
            post_reads.append(post_id)
            return original(session, post_id)

        monkeypatch.setattr(observation_references, "get_post", read_post)
        command = SocialObservationCommand(
            world_id=fixture.world.id,
            observer_world_character_id=fixture.target_world_character.id,
            source_social_event_id=fixture.event.id,
            source_post_id=fixture.reply_post.id,
            lane="inbox",
            observed_at=datetime(2026, 9, 6, 1, 0, tzinfo=UTC),
        )
        with pytest.raises(SocialObservationError) as error:
            observations.observe(
                db, command,
                references=observation_references.SqlAlchemyObservationReferences(db),
            )
        assert error.value.reason_code == reason
        assert post_reads == ([fixture.reply_post.id] if reads_post else [])
        assert _counts(db) == before
        db.rollback()
    engine.dispose()
