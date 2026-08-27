from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.compatibility.manual_social.observations import observe_source
from app.core.db import Base
from app.domains.social.public import SocialObservationError
from app.services import (
    activity_proposal_runtime,
    langgraph_social_apply,
    social_event_runtime,
    world_character_contracts,
)
from app.services.graph_projection_commands import (
    RelationshipStateProjectionCommand,
    build_projection_command,
)


@dataclass(frozen=True)
class SocialFixture:
    world: models.World
    actor: models.Character
    actor_world_character: models.WorldCharacter
    target: models.Character
    target_world_character: models.WorldCharacter


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _user(suffix: str) -> models.User:
    return models.User(
        id=f"user-social-{suffix}",
        email=f"social-{suffix}@example.test",
        display_name=f"Social {suffix}",
        display_name_normalized=f"social {suffix}",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )


def _character(user: models.User, suffix: str) -> models.Character:
    return models.Character(
        id=f"character-social-{suffix}",
        owner_id=user.id,
        name=f"Character {suffix}",
        handle=f"social-{suffix}",
        one_liner="An academy resident",
        personality="Curious and considerate.",
        speech_style="Friendly and concise.",
        worldview="Shared experiences shape relationships.",
        topic_preferences="Alchemy and friendship",
        safety_rules="Avoid dangerous experiments.",
        persona_summary="A resident of Arcana Academy.",
        moderation_status="active",
    )


def _seed(db: Session) -> SocialFixture:
    now = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
    actor_user = _user("actor")
    target_user = _user("target")
    actor = _character(actor_user, "actor")
    target = _character(target_user, "target")
    world = models.World(
        id="world-social-a",
        slug="social-arcana-a",
        owner_user_id=actor_user.id,
        name="Arcana Academy",
        tagline="A practical magic academy",
        setting_description="Students study magic together.",
        daily_life_description="Classes and clubs shape each day.",
        genre_tags=["fantasy"],
        tone_tags=["warm"],
        timezone="Asia/Seoul",
        language="ko",
        visibility="public",
        join_policy="open",
        status="published",
        contract_version="world-v1",
        contract_hash="a" * 64,
        readiness_status="publish_ready",
        create_idempotency_key="create-world-social-a",
    )
    db.add_all([actor_user, target_user, actor, target, world])
    db.flush()
    actor_membership = models.WorldMembership(
        id="membership-social-actor",
        world_id=world.id,
        user_id=actor_user.id,
        role="member",
        status="active",
        joined_at=now,
    )
    target_membership = models.WorldMembership(
        id="membership-social-target",
        world_id=world.id,
        user_id=target_user.id,
        role="member",
        status="active",
        joined_at=now,
    )
    db.add_all([actor_membership, target_membership])
    db.flush()
    actor_world_character = models.WorldCharacter(
        id="world-character-social-actor",
        world_id=world.id,
        character_id=actor.id,
        membership_id=actor_membership.id,
        role_key="student",
        status="active",
        character_contract_hash=world_character_contracts.character_contract_hash(actor),
        world_contract_hash=world.contract_hash,
    )
    target_world_character = models.WorldCharacter(
        id="world-character-social-target",
        world_id=world.id,
        character_id=target.id,
        membership_id=target_membership.id,
        role_key="student",
        status="active",
        character_contract_hash=world_character_contracts.character_contract_hash(target),
        world_contract_hash=world.contract_hash,
    )
    db.add_all([actor_world_character, target_world_character])
    db.commit()
    return SocialFixture(
        world,
        actor,
        actor_world_character,
        target,
        target_world_character,
    )


def _post(
    db: Session,
    *,
    post_id: str,
    author: models.Character,
    author_world_character: models.WorldCharacter,
    body: str,
    reply_to_post_id: str | None = None,
) -> models.Post:
    row = models.Post(
        id=post_id,
        author_character_id=author.id,
        world_id=author_world_character.world_id,
        author_world_character_id=author_world_character.id,
        reply_to_post_id=reply_to_post_id,
        author_name=author.name,
        title="Arcana activity",
        body=body,
        visibility="public",
        search_document=body,
    )
    db.add(row)
    db.flush()
    return row


def _record_post_event(
    db: Session,
    *,
    fixture: SocialFixture,
    event_idempotency: str,
    source: models.Post,
    target_post: models.Post,
    event_type: str,
    actor_world_character_id: str,
    target_world_character_id: str,
    comment_purpose: str | None,
    occurred_at: datetime,
) -> social_event_runtime.EventApplyResult:
    return social_event_runtime.record_successful_social_event(
        db,
        world_id=fixture.world.id,
        actor_world_character_id=actor_world_character_id,
        target_world_character_id=target_world_character_id,
        event_type=event_type,
        occurred_at=occurred_at,
        idempotency_key=event_idempotency,
        evidence=social_event_runtime.EvidenceInput(
            evidence_kind="reply_post",
            source_object_type="post",
            source_object_id=source.id,
            root_post_id=target_post.id,
            source_post_id=source.id,
            target_post_id=target_post.id,
            interaction_intent="ordinary_comment",
            comment_purpose=comment_purpose,
            source_text=source.body,
            source_visibility_at_event="public",
            source_author_id_at_event=actor_world_character_id,
        ),
    )


def test_observation_is_directional_idempotent_and_independent_from_follow_up() -> None:
    engine = _engine()
    occurred_at = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        root = _post(
            db,
            post_id="post-observation-root",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="What did you notice in class?",
        )
        reply = _post(
            db,
            post_id="post-observation-source",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="The rune changed color after sunset.",
            reply_to_post_id=root.id,
        )
        source_event = models.SocialEvent(
            id="event-observation-source",
            world_id=fixture.world.id,
            actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=fixture.target_world_character.id,
            event_type="comment_created",
            result="succeeded",
            occurred_at=occurred_at,
            idempotency_key="event-observation-source",
            schema_version="social-event-v1",
            retrieval_status="audit_only",
        )
        db.add(source_event)
        db.flush()
        db.add(
            models.SocialEventEvidence(
                id="evidence-observation-source",
                social_event_id=source_event.id,
                evidence_kind="reply_post",
                source_object_type="post",
                source_object_id=reply.id,
                root_post_id=root.id,
                source_post_id=reply.id,
                target_post_id=root.id,
                source_visibility_at_event="public",
                source_author_id_at_event=fixture.actor_world_character.id,
                occurred_at=occurred_at,
            )
        )
        db.commit()

        # Source success alone is audit evidence, not an inferred relationship.
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0

        observed = observe_source(
            db,
            world_id=fixture.world.id,
            observer_world_character_id=fixture.target_world_character.id,
            source_social_event_id=source_event.id,
            source_post_id=reply.id,
            lane="routine",
            observed_at=occurred_at + timedelta(minutes=1),
        )
        db.commit()

        relationship_state = db.get(
            models.RelationshipState, observed.relationship_state_id
        )
        relationship_change = db.get(
            models.RelationshipStateChange, observed.receipt_id
        )
        assert relationship_state is not None
        assert relationship_change is not None
        assert observed.replayed is False
        assert relationship_state.actor_world_character_id == (
            fixture.target_world_character.id
        )
        assert relationship_state.target_world_character_id == (
            fixture.actor_world_character.id
        )
        assert relationship_state.familiarity == 1
        assert relationship_state.affinity == 0
        assert relationship_state.trust == 0
        assert relationship_state.tension == 0
        assert relationship_change.delta_familiarity == 1

        # Routine, Inbox, and Feed all enter the same production application
        # contract and converge on the already committed canonical receipt.
        lane_replays = [
            observe_source(
                db,
                world_id=fixture.world.id,
                observer_world_character_id=fixture.target_world_character.id,
                source_social_event_id=None,
                source_post_id=reply.id,
                lane=lane,
                observed_at=occurred_at + timedelta(minutes=index + 2),
            )
            for index, lane in enumerate(("routine", "inbox", "feed"))
        ]
        db.commit()
        assert [replay.lane for replay in lane_replays] == [
            "routine",
            "inbox",
            "feed",
        ]
        assert all(replay.replayed for replay in lane_replays)
        assert {replay.receipt_id for replay in lane_replays} == {
            observed.receipt_id
        }
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 1
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 1

        outbox = db.scalar(select(models.GraphProjectionOutbox))
        assert outbox is not None
        assert outbox.payload_version == "relationship-observation-v1"
        command = build_projection_command(db, outbox_id=outbox.id)
        assert isinstance(command, RelationshipStateProjectionCommand)
        assert command.event.actor_world_character_id == fixture.actor_world_character.id
        assert command.actor_world_character_id == fixture.target_world_character.id
        assert command.target_world_character_id == fixture.actor_world_character.id

        # A later follow-up failure is a separate transaction and cannot erase
        # the committed observation or create a partial follow-up event.
        with pytest.raises(RuntimeError, match="follow-up failure"):
            try:
                db.add(
                    models.SocialEvent(
                        id="event-failed-follow-up",
                        world_id=fixture.world.id,
                        actor_world_character_id=fixture.target_world_character.id,
                        target_world_character_id=fixture.actor_world_character.id,
                        event_type="comment_created",
                        result="succeeded",
                        occurred_at=occurred_at + timedelta(minutes=3),
                        idempotency_key="event-failed-follow-up",
                        schema_version="social-event-v1",
                    )
                )
                db.flush()
                raise RuntimeError("follow-up failure")
            except RuntimeError:
                db.rollback()
                raise
        assert db.get(models.RelationshipStateChange, observed.receipt_id)
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 1


def test_observation_revalidates_hidden_source_before_any_relationship_write() -> None:
    engine = _engine()
    occurred_at = datetime(2026, 8, 11, 1, 20, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        source = _post(
            db,
            post_id="post-observation-hidden",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="This post becomes hidden before the observer can read it.",
        )
        source_event = models.SocialEvent(
            id="event-observation-hidden",
            world_id=fixture.world.id,
            actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=None,
            event_type="post_published",
            result="succeeded",
            occurred_at=occurred_at,
            idempotency_key="event-observation-hidden",
            schema_version="social-event-v1",
            retrieval_status="eligible",
        )
        db.add(source_event)
        db.flush()
        db.add(
            models.SocialEventEvidence(
                id="evidence-observation-hidden",
                social_event_id=source_event.id,
                evidence_kind="post",
                source_object_type="post",
                source_object_id=source.id,
                root_post_id=source.id,
                source_post_id=source.id,
                source_visibility_at_event="public",
                source_author_id_at_event=fixture.actor_world_character.id,
                occurred_at=occurred_at,
            )
        )
        db.commit()

        source.visibility = "private"
        db.commit()

        with pytest.raises(SocialObservationError) as exc_info:
            observe_source(
                db,
                world_id=fixture.world.id,
                observer_world_character_id=fixture.target_world_character.id,
                source_social_event_id=source_event.id,
                source_post_id=source.id,
                lane="inbox",
                observed_at=occurred_at + timedelta(minutes=1),
            )
        db.rollback()

        assert exc_info.value.reason_code == "evidence_source_hidden"
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0


def test_successful_comment_creates_canonical_evidence_directional_state_and_outbox_once() -> None:
    engine = _engine()
    occurred_at = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        root = _post(
            db,
            post_id="post-social-root",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="I am testing a new potion formula.",
        )
        reply = _post(
            db,
            post_id="post-social-reply",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="That sounds exciting. I hope it goes well.",
            reply_to_post_id=root.id,
        )
        result = _record_post_event(
            db,
            fixture=fixture,
            event_idempotency="social-comment-once",
            source=reply,
            target_post=root,
            event_type="comment_created",
            actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=fixture.target_world_character.id,
            comment_purpose="encouragement",
            occurred_at=occurred_at,
        )
        db.commit()

        replay = _record_post_event(
            db,
            fixture=fixture,
            event_idempotency="social-comment-once",
            source=reply,
            target_post=root,
            event_type="comment_created",
            actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=fixture.target_world_character.id,
            comment_purpose="encouragement",
            occurred_at=occurred_at,
        )
        db.commit()

        assert result.reused is False
        assert replay.reused is True
        assert replay.event.id == result.event.id
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 1
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 1
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 1
        state = result.relationship_state
        assert state is not None
        assert state.actor_world_character_id == fixture.actor_world_character.id
        assert state.target_world_character_id == fixture.target_world_character.id
        assert (state.familiarity, state.affinity, state.trust, state.tension) == (
            2,
            1,
            0,
            0,
        )
        assert state.interaction_count == 1
        assert db.scalar(
            select(models.RelationshipState.id).where(
                models.RelationshipState.actor_world_character_id
                == fixture.target_world_character.id,
                models.RelationshipState.target_world_character_id
                == fixture.actor_world_character.id,
            )
        ) is None
        evidence = db.scalar(select(models.SocialEventEvidence))
        assert evidence is not None
        assert evidence.source_object_id == reply.id
        assert evidence.content_sha256 is not None


def test_reverse_reply_creates_separate_directional_relationship() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        root = _post(
            db,
            post_id="post-direction-root",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="The potion changed color.",
        )
        actor_reply = _post(
            db,
            post_id="post-direction-actor-reply",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="Try lowering the heat.",
            reply_to_post_id=root.id,
        )
        _record_post_event(
            db,
            fixture=fixture,
            event_idempotency="direction-actor-target",
            source=actor_reply,
            target_post=root,
            event_type="comment_created",
            actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=fixture.target_world_character.id,
            comment_purpose="advice",
            occurred_at=datetime(2026, 8, 11, 1, 0, tzinfo=UTC),
        )
        target_reply = _post(
            db,
            post_id="post-direction-target-reply",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="Thanks. I will try that on the next pass.",
            reply_to_post_id=actor_reply.id,
        )
        reverse = _record_post_event(
            db,
            fixture=fixture,
            event_idempotency="direction-target-actor",
            source=target_reply,
            target_post=actor_reply,
            event_type="reply_created",
            actor_world_character_id=fixture.target_world_character.id,
            target_world_character_id=fixture.actor_world_character.id,
            comment_purpose="encouragement",
            occurred_at=datetime(2026, 8, 11, 1, 5, tzinfo=UTC),
        )
        db.commit()

        states = list(
            db.scalars(
                select(models.RelationshipState).order_by(
                    models.RelationshipState.actor_world_character_id
                )
            )
        )
        assert len(states) == 2
        assert reverse.relationship_state is not None
        assert reverse.relationship_state.actor_world_character_id == (
            fixture.target_world_character.id
        )
        assert reverse.relationship_state.target_world_character_id == (
            fixture.actor_world_character.id
        )
        assert (
            reverse.relationship_state.familiarity,
            reverse.relationship_state.affinity,
            reverse.relationship_state.trust,
        ) == (2, 2, 1)


def test_inbox_reply_apply_marks_notification_and_updates_only_actor_direction() -> None:
    engine = _engine()
    occurred_at = datetime(2026, 8, 11, 2, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        target_post = _post(
            db,
            post_id="post-inbox-target",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="The greenhouse is quiet this morning.",
        )
        reply = _post(
            db,
            post_id="post-inbox-reply",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="I will stop by after class.",
            reply_to_post_id=target_post.id,
        )
        db.add(
            models.CharacterActiveWorld(
                character_id=fixture.actor.id,
                world_character_id=fixture.actor_world_character.id,
                selected_at=occurred_at,
                idempotency_key="active-world-social-actor",
                version=1,
            )
        )
        run = models.AgentRun(
            id="run-inbox-reply",
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
            agent_id="agent-inbox-reply",
            session_key="session-inbox-reply",
            status="running",
        )
        db.add(run)
        db.flush()
        execution = models.AgentPublicActionExecution(
            run_id=run.id,
            character_id=fixture.actor.id,
            signature="signature-inbox-reply",
            scope="inbox",
            action_type="reply",
            target_post_id=target_post.id,
            interaction_intent="ordinary_comment",
            comment_purpose="encouragement",
            status="succeeded",
            result={"post_id": reply.id, "reply_to_post_id": target_post.id},
        )
        notification = models.Notification(
            recipient_character_id=fixture.actor.id,
            actor_character_id=fixture.target.id,
            world_id=fixture.world.id,
            recipient_world_character_id=fixture.actor_world_character.id,
            actor_world_character_id=fixture.target_world_character.id,
            notification_type="reply",
            post_id=target_post.id,
            source_post_id=target_post.id,
        )
        db.add_all([execution, notification])
        db.flush()

        applied = langgraph_social_apply.apply_successful_public_action(
            db,
            actor_character_id=fixture.actor.id,
            action_type="reply",
            target_post_id=target_post.id,
            target_character_id=None,
            action_result={"post_id": reply.id, "reply_to_post_id": target_post.id},
            execution=execution,
            occurred_at=occurred_at,
            notification_id=notification.id,
            source_text=reply.body,
        )
        db.commit()

        db.refresh(notification)
        assert applied.event.event_type == "reply_created"
        assert notification.read_at.replace(tzinfo=UTC) == occurred_at
        assert notification.handled_at.replace(tzinfo=UTC) == occurred_at
        assert notification.handling_outcome == "reply"
        assert execution.social_event_id == applied.event.id
        actor_state = db.scalar(
            select(models.RelationshipState).where(
                models.RelationshipState.actor_world_character_id
                == fixture.actor_world_character.id,
                models.RelationshipState.target_world_character_id
                == fixture.target_world_character.id,
            )
        )
        reverse_state = db.scalar(
            select(models.RelationshipState).where(
                models.RelationshipState.actor_world_character_id
                == fixture.target_world_character.id,
                models.RelationshipState.target_world_character_id
                == fixture.actor_world_character.id,
            )
        )
        assert actor_state is not None
        assert reverse_state is None


def test_inbox_llm_no_action_marks_notification_without_event_or_relationship() -> None:
    engine = _engine()
    occurred_at = datetime(2026, 8, 11, 2, 30, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        target_post = _post(
            db,
            post_id="post-inbox-no-action",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="A small observation that needs no reply.",
        )
        db.add(
            models.CharacterActiveWorld(
                character_id=fixture.actor.id,
                world_character_id=fixture.actor_world_character.id,
                selected_at=occurred_at,
                idempotency_key="active-world-social-no-action",
                version=1,
            )
        )
        notification = models.Notification(
            recipient_character_id=fixture.actor.id,
            actor_character_id=fixture.target.id,
            world_id=fixture.world.id,
            recipient_world_character_id=fixture.actor_world_character.id,
            actor_world_character_id=fixture.target_world_character.id,
            notification_type="reply",
            post_id=target_post.id,
            source_post_id=target_post.id,
        )
        db.add(notification)
        db.flush()

        langgraph_social_apply.mark_notification_handled_without_public_action(
            db,
            actor_character_id=fixture.actor.id,
            notification_id=notification.id,
            handling_outcome="LLM_DECIDED_NO_ACTION",
            occurred_at=occurred_at,
        )
        db.commit()

        db.refresh(notification)
        assert notification.read_at.replace(tzinfo=UTC) == occurred_at
        assert notification.handled_at.replace(tzinfo=UTC) == occurred_at
        assert notification.handling_outcome == "LLM_DECIDED_NO_ACTION"
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 0


def test_comment_daily_cap_preserves_events_and_interaction_count_without_extra_delta() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        root = _post(
            db,
            post_id="post-cap-root",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="Today I am recording five observations.",
        )
        changes: list[models.RelationshipStateChange] = []
        for index in range(5):
            reply = _post(
                db,
                post_id=f"post-cap-reply-{index}",
                author=fixture.actor,
                author_world_character=fixture.actor_world_character,
                body=f"Observation {index}",
                reply_to_post_id=root.id,
            )
            result = _record_post_event(
                db,
                fixture=fixture,
                event_idempotency=f"cap-comment-{index}",
                source=reply,
                target_post=root,
                event_type="comment_created",
                actor_world_character_id=fixture.actor_world_character.id,
                target_world_character_id=fixture.target_world_character.id,
                comment_purpose="observation",
                occurred_at=datetime(2026, 8, 11, 2, index, tzinfo=UTC),
            )
            assert result.relationship_change is not None
            changes.append(result.relationship_change)
        db.commit()

        state = db.scalar(select(models.RelationshipState))
        assert state is not None
        assert state.familiarity == 8
        assert state.interaction_count == 5
        assert [change.applied for change in changes] == [True, True, True, True, False]
        assert changes[-1].not_applied_reason == "daily_delta_cap"
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 5
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 5
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 5


def test_transaction_rollback_removes_event_evidence_relationship_and_outbox() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        root = _post(
            db,
            post_id="post-rollback-root",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="This source row remains committed.",
        )
        reply = _post(
            db,
            post_id="post-rollback-reply",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="This attempted action will roll back.",
            reply_to_post_id=root.id,
        )
        db.commit()

        _record_post_event(
            db,
            fixture=fixture,
            event_idempotency="rollback-event",
            source=reply,
            target_post=root,
            event_type="comment_created",
            actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=fixture.target_world_character.id,
            comment_purpose="observation",
            occurred_at=datetime(2026, 8, 11, 3, 0, tzinfo=UTC),
        )
        db.rollback()

        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0
        assert db.get(models.Post, root.id) is not None
        assert db.get(models.Post, reply.id) is not None


def test_self_target_and_cross_world_target_are_rejected() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        root = _post(
            db,
            post_id="post-invalid-root",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="Invalid target fixture.",
        )
        reply = _post(
            db,
            post_id="post-invalid-reply",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="Invalid relation attempt.",
            reply_to_post_id=root.id,
        )
        db.commit()

        with pytest.raises(
            social_event_runtime.SocialEventRuntimeError,
            match="self_target_forbidden",
        ):
            _record_post_event(
                db,
                fixture=fixture,
                event_idempotency="self-target",
                source=reply,
                target_post=root,
                event_type="comment_created",
                actor_world_character_id=fixture.actor_world_character.id,
                target_world_character_id=fixture.actor_world_character.id,
                comment_purpose="observation",
                occurred_at=datetime(2026, 8, 11, 4, 0, tzinfo=UTC),
            )

        with pytest.raises(
            social_event_runtime.SocialEventRuntimeError,
            match="cross_world_reference",
        ):
            _record_post_event(
                db,
                fixture=fixture,
                event_idempotency="missing-world-target",
                source=reply,
                target_post=root,
                event_type="comment_created",
                actor_world_character_id=fixture.actor_world_character.id,
                target_world_character_id="world-character-from-another-world",
                comment_purpose="observation",
                occurred_at=datetime(2026, 8, 11, 4, 5, tzinfo=UTC),
            )

        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0


def test_source_deletion_retains_audit_rows_and_emits_one_exclusion() -> None:
    from app.services import community, social_memory_read, social_routine_interactions

    engine = _engine()
    occurred_at = datetime(2026, 8, 11, 5, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        root = _post(
            db,
            post_id="post-exclusion-root",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="I am waiting in the greenhouse.",
        )
        reply = _post(
            db,
            post_id="post-exclusion-reply",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="I will bring the watering can.",
            reply_to_post_id=root.id,
        )
        result = _record_post_event(
            db,
            fixture=fixture,
            event_idempotency="source-exclusion-event",
            source=reply,
            target_post=root,
            event_type="comment_created",
            actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=fixture.target_world_character.id,
            comment_purpose="encouragement",
            occurred_at=occurred_at,
        )
        db.commit()
        source = social_routine_interactions.CanonicalRoutineInteractionSource()
        before_delete = source.candidates(
            db,
            world_id=fixture.world.id,
            consumer_world_character_id=fixture.target_world_character.id,
            episode_id="episode-source-deletion",
            after=occurred_at - timedelta(minutes=1),
            before=occurred_at + timedelta(minutes=1),
        )
        assert [row.source_event_id for row in before_delete] == [
            result.event.id
        ]
        assert result.relationship_state is not None
        relationship_id = result.relationship_state.id
        before = (
            result.relationship_state.familiarity,
            result.relationship_state.affinity,
            result.relationship_state.interaction_count,
        )

        owner = db.get(models.User, fixture.actor.owner_id)
        assert owner is not None
        community.delete_post(db, owner, reply.id)
        deleted_reply = db.get(models.Post, reply.id)
        assert deleted_reply is not None
        assert deleted_reply.deleted_at is not None
        repeated = social_event_runtime.exclude_events_for_posts(
            db,
            post_ids=[reply.id],
            reason="source_deleted",
            invalidated_at=deleted_reply.deleted_at,
        )
        db.commit()

        event_row = db.get(models.SocialEvent, result.event.id)
        relationship = db.get(models.RelationshipState, relationship_id)
        outboxes = list(
            db.scalars(
                select(models.GraphProjectionOutbox).order_by(
                    models.GraphProjectionOutbox.projection_type
                )
            )
        )
        assert repeated == 0
        assert event_row is not None
        assert event_row.retrieval_status == "excluded"
        assert event_row.invalidation_reason == "source_deleted"
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 1
        assert relationship is not None
        assert (
            relationship.familiarity,
            relationship.affinity,
            relationship.interaction_count,
        ) == before
        assert [row.projection_type for row in outboxes] == [
            "relationship_state",
            "source_exclusion",
        ]
        exclusion = next(
            row for row in outboxes if row.projection_type == "source_exclusion"
        )
        assert exclusion.payload == {
            "world_id": fixture.world.id,
            "source_event_id": result.event.id,
            "reason": "source_deleted",
        }
        assert exclusion.payload_version == "source-exclusion-v1"

        diagnostics = social_memory_read.get_owner_diagnostics(
            db,
            character_id=fixture.actor.id,
            world_id=fixture.world.id,
            user=owner,
        )
        assert diagnostics.recent_events[0].retrieval_status == "excluded"
        assert diagnostics.recent_events[0].evidence[0].source_status == "excluded"
        assert (
            diagnostics.recent_events[0].evidence[0].exclusion_reason
            == "source_deleted"
        )
        after_delete = source.candidates(
            db,
            world_id=fixture.world.id,
            consumer_world_character_id=fixture.target_world_character.id,
            episode_id="episode-source-deletion",
            after=occurred_at - timedelta(minutes=1),
            before=occurred_at + timedelta(minutes=1),
        )
        assert after_delete == []


def test_same_character_pair_is_isolated_across_world_events_relationships_and_proposals() -> None:
    from app.services import social_memory_read, social_routine_interactions

    engine = _engine()
    occurred_at = datetime(2026, 8, 11, 5, 30, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor_user = db.get(models.User, fixture.actor.owner_id)
        target_user = db.get(models.User, fixture.target.owner_id)
        assert actor_user is not None
        assert target_user is not None
        other_world = models.World(
            id="world-social-b",
            slug="social-arcana-b",
            owner_user_id=actor_user.id,
            name="Arcana Academy Mirror",
            tagline="A separate academy timeline",
            setting_description="The same characters live in another timeline.",
            daily_life_description="Separate classes and clubs shape each day.",
            genre_tags=["fantasy"],
            tone_tags=["mysterious"],
            timezone="Asia/Seoul",
            language="ko",
            visibility="public",
            join_policy="open",
            status="published",
            contract_version="world-v1",
            contract_hash="b" * 64,
            readiness_status="publish_ready",
            create_idempotency_key="create-world-social-b",
        )
        db.add(other_world)
        db.flush()
        actor_membership = models.WorldMembership(
            id="membership-social-b-actor",
            world_id=other_world.id,
            user_id=actor_user.id,
            role="member",
            status="active",
            joined_at=occurred_at,
        )
        target_membership = models.WorldMembership(
            id="membership-social-b-target",
            world_id=other_world.id,
            user_id=target_user.id,
            role="member",
            status="active",
            joined_at=occurred_at,
        )
        db.add_all([actor_membership, target_membership])
        db.flush()
        actor_world_character = models.WorldCharacter(
            id="world-character-social-b-actor",
            world_id=other_world.id,
            character_id=fixture.actor.id,
            membership_id=actor_membership.id,
            role_key="student",
            status="active",
            character_contract_hash=world_character_contracts.character_contract_hash(
                fixture.actor
            ),
            world_contract_hash=other_world.contract_hash,
        )
        target_world_character = models.WorldCharacter(
            id="world-character-social-b-target",
            world_id=other_world.id,
            character_id=fixture.target.id,
            membership_id=target_membership.id,
            role_key="student",
            status="active",
            character_contract_hash=world_character_contracts.character_contract_hash(
                fixture.target
            ),
            world_contract_hash=other_world.contract_hash,
        )
        db.add_all([actor_world_character, target_world_character])
        db.flush()
        other_fixture = SocialFixture(
            other_world,
            fixture.actor,
            actor_world_character,
            fixture.target,
            target_world_character,
        )
        root = _post(
            db,
            post_id="post-social-b-root",
            author=fixture.target,
            author_world_character=target_world_character,
            body="The mirror-world astronomy club is meeting.",
        )
        comment = _post(
            db,
            post_id="post-social-b-comment",
            author=fixture.actor,
            author_world_character=actor_world_character,
            body="I will bring the star chart.",
            reply_to_post_id=root.id,
        )
        ordinary = _record_post_event(
            db,
            fixture=other_fixture,
            event_idempotency="social-b-comment",
            source=comment,
            target_post=root,
            event_type="comment_created",
            actor_world_character_id=actor_world_character.id,
            target_world_character_id=target_world_character.id,
            comment_purpose="observation",
            occurred_at=occurred_at,
        )
        proposal_comment = _post(
            db,
            post_id="post-social-b-proposal",
            author=fixture.actor,
            author_world_character=actor_world_character,
            body="Let's compare the mirror-world records tomorrow evening.",
            reply_to_post_id=root.id,
        )
        proposal_event = social_event_runtime.record_successful_social_event(
            db,
            world_id=other_world.id,
            actor_world_character_id=actor_world_character.id,
            target_world_character_id=target_world_character.id,
            event_type="joint_proposed",
            occurred_at=occurred_at + timedelta(minutes=1),
            idempotency_key="social-b-joint-proposed",
            evidence=social_event_runtime.EvidenceInput(
                evidence_kind="reply_post",
                source_object_type="post",
                source_object_id=proposal_comment.id,
                root_post_id=root.id,
                source_post_id=proposal_comment.id,
                target_post_id=root.id,
                interaction_intent="joint_activity_proposal",
                source_text=proposal_comment.body,
                source_visibility_at_event="public",
                source_author_id_at_event=actor_world_character.id,
            ),
        ).event
        proposal = activity_proposal_runtime.create_published_proposal(
            db,
            preview=schemas.JointActivityProposalPreview(
                text=proposal_comment.body,
                source_post_id=root.id,
                activity_seed="Compare the mirror-world observatory records.",
                target_world_character_id=target_world_character.id,
                place_key=None,
                target_daypart="evening",
                date_policy="exact",
                target_date=date(2026, 8, 12),
            ),
            proposal_comment=proposal_comment,
            proposal_event=proposal_event,
            proposer_world_character_id=actor_world_character.id,
            now=occurred_at + timedelta(minutes=1),
        )
        db.commit()

        world_a = social_memory_read.get_owner_diagnostics(
            db,
            character_id=fixture.actor.id,
            world_id=fixture.world.id,
            user=actor_user,
        )
        world_b = social_memory_read.get_owner_diagnostics(
            db,
            character_id=fixture.actor.id,
            world_id=other_world.id,
            user=actor_user,
        )
        source = social_routine_interactions.CanonicalRoutineInteractionSource()
        world_a_prompt = source.candidates(
            db,
            world_id=fixture.world.id,
            consumer_world_character_id=fixture.target_world_character.id,
            episode_id="episode-world-a",
            after=occurred_at - timedelta(minutes=1),
            before=occurred_at + timedelta(minutes=2),
        )
        world_b_prompt = source.candidates(
            db,
            world_id=other_world.id,
            consumer_world_character_id=target_world_character.id,
            episode_id="episode-world-b",
            after=occurred_at - timedelta(minutes=1),
            before=occurred_at + timedelta(minutes=2),
        )

        assert world_a.recent_events == []
        assert world_a.outgoing_relationships == []
        assert world_a.incoming_relationships == []
        assert world_a.open_proposals == []
        assert world_a_prompt == []
        assert {row.id for row in world_b.recent_events} == {
            ordinary.event.id,
            proposal_event.id,
        }
        assert len(world_b.outgoing_relationships) == 1
        assert (
            world_b.outgoing_relationships[0].actor_world_character_id
            == actor_world_character.id
        )
        assert [row.id for row in world_b.open_proposals] == [proposal.id]
        assert [row.source_event_id for row in world_b_prompt] == [
            ordinary.event.id
        ]


def test_read_revalidates_membership_and_block_before_exposing_evidence() -> None:
    from app.services import social_memory_read

    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        root = _post(
            db,
            post_id="post-revalidation-root",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="The astronomy club is meeting tonight.",
        )
        reply = _post(
            db,
            post_id="post-revalidation-reply",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="I would like to join.",
            reply_to_post_id=root.id,
        )
        _record_post_event(
            db,
            fixture=fixture,
            event_idempotency="revalidation-event",
            source=reply,
            target_post=root,
            event_type="comment_created",
            actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=fixture.target_world_character.id,
            comment_purpose="observation",
            occurred_at=datetime(2026, 8, 11, 6, 0, tzinfo=UTC),
        )
        db.commit()
        owner = db.get(models.User, fixture.actor.owner_id)
        membership = db.get(
            models.WorldMembership,
            fixture.target_world_character.membership_id,
        )
        assert owner is not None
        assert membership is not None

        membership.status = "left"
        db.commit()
        diagnostics = social_memory_read.get_owner_diagnostics(
            db,
            character_id=fixture.actor.id,
            world_id=fixture.world.id,
            user=owner,
        )
        assert (
            diagnostics.recent_events[0].evidence[0].exclusion_reason
            == "membership_inactive"
        )

        membership.status = "active"
        db.add(
            models.WorldCharacterBlock(
                id="block-social-revalidation",
                world_id=fixture.world.id,
                blocker_world_character_id=fixture.target_world_character.id,
                blocked_world_character_id=fixture.actor_world_character.id,
            )
        )
        db.commit()
        diagnostics = social_memory_read.get_owner_diagnostics(
            db,
            character_id=fixture.actor.id,
            world_id=fixture.world.id,
            user=owner,
        )
        assert diagnostics.recent_events[0].evidence[0].exclusion_reason == "blocked"

        with pytest.raises(
            social_event_runtime.SocialEventRuntimeError,
            match="world_character_blocked",
        ):
            _record_post_event(
                db,
                fixture=fixture,
                event_idempotency="blocked-event",
                source=reply,
                target_post=root,
                event_type="comment_created",
                actor_world_character_id=fixture.actor_world_character.id,
                target_world_character_id=fixture.target_world_character.id,
                comment_purpose="observation",
                occurred_at=datetime(2026, 8, 11, 6, 5, tzinfo=UTC),
            )
