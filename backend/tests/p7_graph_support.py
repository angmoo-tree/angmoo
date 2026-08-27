from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.core.db import Base
from app.runtime.relationships import (
    sqlalchemy_social_event as social_event_runtime,
)
from app.services import world_character_contracts


@dataclass(frozen=True)
class P7Fixture:
    world: models.World
    owner: models.User
    other_owner: models.User
    actor: models.Character
    target: models.Character
    actor_world_character: models.WorldCharacter
    target_world_character: models.WorldCharacter
    root_post: models.Post
    reply_post: models.Post
    event: models.SocialEvent
    relationship: models.RelationshipState
    outbox: models.GraphProjectionOutbox


def sqlite_engine():
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


def seed_projection_fixture(db: Session, *, suffix: str = "base") -> P7Fixture:
    now = datetime(2026, 8, 12, 1, 0, tzinfo=UTC)
    owner = models.User(
        id=f"p7-owner-{suffix}",
        email=f"p7-owner-{suffix}@example.test",
        display_name=f"P7 Owner {suffix}",
        display_name_normalized=f"p7 owner {suffix}",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )
    other_owner = models.User(
        id=f"p7-other-{suffix}",
        email=f"p7-other-{suffix}@example.test",
        display_name=f"P7 Other {suffix}",
        display_name_normalized=f"p7 other {suffix}",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )
    actor = models.Character(
        id=f"p7-actor-{suffix}",
        owner_id=owner.id,
        name="Mango",
        handle=f"p7-mango-{suffix}",
        one_liner="A curious academy resident",
        personality="Curious and considerate.",
        speech_style="Friendly and concise.",
        worldview="Shared experiences shape relationships.",
        topic_preferences="Magic and friendship",
        safety_rules="Avoid dangerous experiments.",
        persona_summary="An Arcana Academy resident.",
        moderation_status="active",
    )
    target = models.Character(
        id=f"p7-target-{suffix}",
        owner_id=other_owner.id,
        name="Sage",
        handle=f"p7-sage-{suffix}",
        one_liner="A careful potion researcher",
        personality="Calm and observant.",
        speech_style="Measured and warm.",
        worldview="Evidence makes magic safer.",
        topic_preferences="Potions and gardens",
        safety_rules="Check every formula twice.",
        persona_summary="An Arcana Academy researcher.",
        moderation_status="active",
    )
    world = models.World(
        id=f"p7-world-{suffix}",
        slug=f"p7-arcana-{suffix}",
        owner_user_id=owner.id,
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
        create_idempotency_key=f"p7-create-world-{suffix}",
    )
    db.add_all([owner, other_owner, actor, target, world])
    db.flush()
    actor_membership = models.WorldMembership(
        id=f"p7-membership-actor-{suffix}",
        world_id=world.id,
        user_id=owner.id,
        role="member",
        status="active",
        joined_at=now,
    )
    target_membership = models.WorldMembership(
        id=f"p7-membership-target-{suffix}",
        world_id=world.id,
        user_id=other_owner.id,
        role="member",
        status="active",
        joined_at=now,
    )
    db.add_all([actor_membership, target_membership])
    db.flush()
    actor_world_character = models.WorldCharacter(
        id=f"p7-wc-actor-{suffix}",
        world_id=world.id,
        character_id=actor.id,
        membership_id=actor_membership.id,
        role_key="student",
        status="active",
        character_contract_hash=world_character_contracts.character_contract_hash(actor),
        world_contract_hash=world.contract_hash,
    )
    target_world_character = models.WorldCharacter(
        id=f"p7-wc-target-{suffix}",
        world_id=world.id,
        character_id=target.id,
        membership_id=target_membership.id,
        role_key="researcher",
        status="active",
        character_contract_hash=world_character_contracts.character_contract_hash(target),
        world_contract_hash=world.contract_hash,
    )
    db.add_all([actor_world_character, target_world_character])
    db.flush()
    root_post = models.Post(
        id=f"p7-root-{suffix}",
        author_character_id=target.id,
        world_id=world.id,
        author_world_character_id=target_world_character.id,
        author_name=target.name,
        title="Potion notes",
        body="The potion changed color near the garden.",
        visibility="public",
        search_document="potion garden",
    )
    reply_post = models.Post(
        id=f"p7-reply-{suffix}",
        author_character_id=actor.id,
        world_id=world.id,
        author_world_character_id=actor_world_character.id,
        reply_to_post_id=root_post.id,
        author_name=actor.name,
        title="A useful reply",
        body="Try lowering the heat. I can help after class.",
        visibility="public",
        search_document="potion help",
    )
    db.add_all([root_post, reply_post])
    db.flush()
    result = social_event_runtime.record_successful_social_event(
        db,
        world_id=world.id,
        actor_world_character_id=actor_world_character.id,
        target_world_character_id=target_world_character.id,
        event_type="comment_created",
        occurred_at=now,
        idempotency_key=f"p7-comment-{suffix}",
        evidence=social_event_runtime.EvidenceInput(
            evidence_kind="reply_post",
            source_object_type="post",
            source_object_id=reply_post.id,
            root_post_id=root_post.id,
            source_post_id=reply_post.id,
            target_post_id=root_post.id,
            interaction_intent="ordinary_comment",
            comment_purpose="advice",
            source_text=reply_post.body,
            source_visibility_at_event="public",
            source_author_id_at_event=actor_world_character.id,
        ),
    )
    db.commit()
    relationship = result.relationship_state
    assert relationship is not None
    outbox = db.scalar(
        select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.source_event_id == result.event.id
        )
    )
    assert outbox is not None
    return P7Fixture(
        world=world,
        owner=owner,
        other_owner=other_owner,
        actor=actor,
        target=target,
        actor_world_character=actor_world_character,
        target_world_character=target_world_character,
        root_post=root_post,
        reply_post=reply_post,
        event=result.event,
        relationship=relationship,
        outbox=outbox,
    )
