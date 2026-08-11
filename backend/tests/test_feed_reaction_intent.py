from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.core.db import Base
from app.core.search_text import build_post_search_document
from app.services import agent_activity_policy, world_character_contracts
from app.services.direct_llm import RunLlmTracker
from app.services.feed_reaction_planner import validate_reaction_decision
from app.services.resident_contracts import LangGraphResidentContext
from app.services.world_feed_runtime import run_world_keyword_feed


KEYWORDS = [
    "alchemy",
    "library",
    "runes",
    "potions",
    "academy",
    "garden",
    "research",
    "friendship",
]


class FakeFeedProvider:
    def __init__(self, decision: schemas.FeedReactionDecision) -> None:
        self.decision = decision
        self.plan_calls = 0
        self.writer_calls = 0

    async def plan(self, **_kwargs) -> schemas.FeedReactionDecision:
        self.plan_calls += 1
        return self.decision

    async def write_comment(
        self,
        *,
        candidate: schemas.WorldFeedCandidateRead,
        decision: schemas.FeedReactionDecision,
        **_kwargs,
    ) -> schemas.FeedCommentDraft:
        self.writer_calls += 1
        return schemas.FeedCommentDraft(
            text="그 기록 흥미롭다. 다음 실험에서는 어떤 향이 났는지 궁금해!",
            source_post_id=candidate.post_id,
            interaction_intent="ordinary_comment",
            comment_purpose=decision.comment_purpose,
        )


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
        id=f"user-{suffix}",
        email=f"{suffix}@example.test",
        display_name=f"User {suffix}",
        display_name_normalized=f"user {suffix}",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )


def _character(user: models.User, suffix: str) -> models.Character:
    return models.Character(
        id=f"character-{suffix}",
        owner_id=user.id,
        name=f"Character {suffix}",
        handle=f"character-{suffix}",
        one_liner="A curious academy resident",
        personality="Curious and warm.",
        speech_style="Friendly and concise.",
        worldview="Small discoveries matter.",
        topic_preferences="Alchemy and books.",
        safety_rules="Avoid dangerous experiments.",
        persona_summary="An alchemy student at Arcana Academy.",
        moderation_status="active",
    )


def _action_profile() -> dict[str, dict[str, object]]:
    return {
        action: {"weight": 70, "note": f"Use {action} when it fits."}
        for action in (
            "comment",
            "reply",
            "like",
            "repost",
            "follow",
            "unfollow",
            "observe",
        )
    }


def _seed(db: Session, *, with_candidate: bool):
    now = datetime(2026, 8, 11, 7, 0, tzinfo=UTC)
    owner = _user("owner")
    actor = _character(owner, "actor")
    credential = models.LlmCredential(
        id="credential-actor",
        owner_id=owner.id,
        character_id=actor.id,
        provider="google",
        purpose="agent",
        model="gemini-test",
        auth_profile_id="profile-actor",
        label="Fixture key",
        encrypted_api_key="unused-by-fake-provider",
        key_fingerprint="fixture-key",
        enabled=True,
    )
    world = models.World(
        id="world-a",
        slug="arcana-a",
        owner_user_id=owner.id,
        name="Arcana Academy",
        tagline="A practical magic academy",
        setting_description="Students study magic together.",
        daily_life_description="Classes, meals, and clubs shape each day.",
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
        create_idempotency_key="create-world-a",
    )
    db.add_all([owner, actor, credential, world])
    db.flush()
    actor_membership = models.WorldMembership(
        id="membership-actor",
        world_id=world.id,
        user_id=owner.id,
        role="member",
        status="active",
        joined_at=now,
    )
    db.add(actor_membership)
    db.flush()
    actor_hash = world_character_contracts.character_contract_hash(actor)
    actor_wc = models.WorldCharacter(
        id="world-character-actor",
        world_id=world.id,
        character_id=actor.id,
        membership_id=actor_membership.id,
        role_key="student",
        status="active",
        autonomous_enabled=True,
        activity_runtime_mode="routine_resident_v1",
        feed_runtime_mode="keyword_search_v1",
        local_profile={"background": "alchemy student"},
        character_contract_hash=actor_hash,
        world_contract_hash=world.contract_hash,
    )
    db.add(actor_wc)
    db.flush()
    db.add_all(
        [
            models.CharacterActiveWorld(
                character_id=actor.id,
                world_character_id=actor_wc.id,
                selected_at=now,
                idempotency_key="active-actor",
                version=1,
            ),
            models.WorldCommunityProfile(
                id="community-profile-actor",
                world_character_id=actor_wc.id,
                status="ready",
                visible_summary="A curious academy community participant.",
                core_interests=["alchemy", "library", "runes"],
                adjacent_interests=["garden", "friendship"],
                avoid_topics=["dangerous magic"],
                discovery_openness=70,
                search_keywords=KEYWORDS,
                action_profile=_action_profile(),
                schema_version=1,
                generator_version="fixture-v1",
                character_contract_hash=actor_hash,
                world_contract_hash=world.contract_hash,
                provider="google",
                model="gemini-test",
                credential_id=credential.id,
                generated_at=now,
                approved_at=now,
            ),
            models.AgentRun(
                id="run-feed",
                user_id=owner.id,
                character_id=actor.id,
                credential_id=credential.id,
                agent_id="agent-feed",
                session_key="fixture-session-feed",
                status="running",
            ),
        ]
    )
    db.flush()
    target_post = None
    if with_candidate:
        author_user = _user("author")
        author = _character(author_user, "author")
        db.add_all([author_user, author])
        db.flush()
        author_membership = models.WorldMembership(
            id="membership-author",
            world_id=world.id,
            user_id=author_user.id,
            role="member",
            status="active",
            joined_at=now,
        )
        db.add(author_membership)
        db.flush()
        author_wc = models.WorldCharacter(
            id="world-character-author",
            world_id=world.id,
            character_id=author.id,
            membership_id=author_membership.id,
            role_key="student",
            status="active",
            autonomous_enabled=True,
            activity_runtime_mode="routine_resident_v1",
            local_profile={"background": "potion researcher"},
            character_contract_hash=world_character_contracts.character_contract_hash(
                author
            ),
            world_contract_hash=world.contract_hash,
        )
        db.add(author_wc)
        db.flush()
        target_post = models.Post(
            id="post-target",
            author_user_id=author_user.id,
            author_character_id=author.id,
            world_id=world.id,
            author_world_character_id=author_wc.id,
            author_name=author.name,
            title="Alchemy club experiment",
            body="I recorded the color and scent of a new potion.",
            topic_signature="alchemy research",
            search_document=build_post_search_document(
                title="Alchemy club experiment",
                body="I recorded the color and scent of a new potion.",
                topic_signature="alchemy research",
            ),
            created_at=now - timedelta(days=2),
        )
        db.add(target_post)
    db.commit()
    policy = agent_activity_policy.ActivityPolicy(
        within_active_hours=True,
        allowed_actions=("post", "reply", "like", "repost", "follow", "observe"),
        blocked_reasons={},
        next_tick_at=now + timedelta(hours=1),
        summary="fixture",
    )
    context = LangGraphResidentContext(
        db=db,
        run_id="run-feed",
        user_id=owner.id,
        agent_id="agent-feed",
        session_key="fixture-session-feed",
        character=actor,
        credential=credential,
        state=None,
        activity_policy=policy,
        selected_post_id=None,
        run_started_at=now,
        run_mode="scheduled",
    )
    return context, target_post


def test_reaction_contract_rejects_public_ignore_and_invalid_action_shape() -> None:
    with pytest.raises(ValidationError):
        schemas.FeedReactionDecision.model_validate(
            {
                "selected_candidate_index": 0,
                "selected_action": "ignore",
                "interaction_intent": None,
                "comment_purpose": None,
                "reason_code": None,
                "brief": "ignore",
            }
        )
    with pytest.raises(ValidationError):
        schemas.FeedReactionDecision(
            selected_candidate_index=0,
            selected_action="comment",
            interaction_intent="ordinary_comment",
            comment_purpose=None,
            reason_code=None,
            brief="comment",
        )


def test_server_rejects_action_not_present_in_candidate_affordances() -> None:
    candidate = schemas.WorldFeedCandidateRead(
        candidate_index=0,
        post_id="post-1",
        author_world_character_id="wc-2",
        author_character_id="character-2",
        author_name="B",
        title="Alchemy",
        body_preview="Note",
        topic_signature="alchemy",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        world_local_datetime="2026-08-01T09:00:00+09:00",
        age_seconds=0,
        age_bucket="recent",
        matched_keywords=["alchemy"],
        matched_fields=["title"],
        rank_score=4,
        allowed_actions=["like"],
    )
    with pytest.raises(ValueError, match="not allowed"):
        validate_reaction_decision(
            schemas.FeedReactionDecision(
                selected_candidate_index=0,
                selected_action="comment",
                interaction_intent="ordinary_comment",
                comment_purpose="question",
                reason_code=None,
                brief="Ask a question.",
            ),
            candidates=(candidate,),
        )


def test_no_candidate_uses_zero_provider_calls() -> None:
    engine = _engine()
    with Session(engine) as db:
        context, _target = _seed(db, with_candidate=False)
        provider = FakeFeedProvider(
            schemas.FeedReactionDecision(
                selected_candidate_index=None,
                selected_action=None,
                interaction_intent=None,
                comment_purpose=None,
                reason_code="model_abstained",
                brief=None,
            )
        )
        result = asyncio.run(run_world_keyword_feed(context, provider=provider))
        assert result["feed_outcome"] == "no_candidate"
        assert provider.plan_calls == 0
        assert provider.writer_calls == 0
        assert result["llm_usage_summary"]["provider_call_count"] == 0


def test_ordinary_comment_is_world_scoped_and_execution_keeps_intent_evidence() -> None:
    engine = _engine()
    with Session(engine) as db:
        context, target = _seed(db, with_candidate=True)
        provider = FakeFeedProvider(
            schemas.FeedReactionDecision(
                selected_candidate_index=0,
                selected_action="comment",
                interaction_intent="ordinary_comment",
                comment_purpose="question",
                reason_code=None,
                brief="Ask naturally about the potion experiment.",
            )
        )
        result = asyncio.run(run_world_keyword_feed(context, provider=provider))
        assert result["feed_outcome"] == "ACTION_SUCCEEDED"
        assert provider.plan_calls == 1
        assert provider.writer_calls == 1
        reply = db.scalar(
            select(models.Post).where(models.Post.reply_to_post_id == target.id)
        )
        assert reply is not None
        assert reply.world_id == target.world_id
        assert reply.author_world_character_id == "world-character-actor"
        observation = db.scalar(select(models.WorldCharacterFeedObservation))
        assert observation.status == "observed"
        assert observation.selected_action == "comment"
        assert observation.interaction_intent == "ordinary_comment"
        assert observation.comment_purpose == "question"
        execution = db.scalar(
            select(models.AgentPublicActionExecution).where(
                models.AgentPublicActionExecution.scope == "world_keyword_feed"
            )
        )
        assert execution.status == "succeeded"
        assert execution.world_id == target.world_id
        assert execution.feed_observation_id == observation.id
        assert execution.action_type == "comment"


def test_same_minute_cycle_is_reused_without_second_provider_call() -> None:
    engine = _engine()
    with Session(engine) as db:
        context, _target = _seed(db, with_candidate=True)
        provider = FakeFeedProvider(
            schemas.FeedReactionDecision(
                selected_candidate_index=None,
                selected_action=None,
                interaction_intent=None,
                comment_purpose=None,
                reason_code="model_abstained",
                brief=None,
            )
        )
        first = asyncio.run(run_world_keyword_feed(context, provider=provider))
        second = asyncio.run(run_world_keyword_feed(context, provider=provider))
        assert first["feed_outcome"] == "model_abstained"
        assert second["feed_outcome"] == "duplicate_cycle"
        assert provider.plan_calls == 1
        assert provider.writer_calls == 0
