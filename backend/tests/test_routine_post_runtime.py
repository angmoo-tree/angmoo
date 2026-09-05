from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from threading import Barrier
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.core.db import Base
from app.cruds import agents as agent_crud
from app.runtime.social.sqlalchemy_unit_of_work import (
    SqlAlchemySocialWriteUnitOfWork,
)
from app.domains.social.public import OwnerReplyCommand, create_owner_reply
from app.providers.gemini import build_generate_content_config
from app.services import (
    activity_state_contracts,
    daily_activity_plans,
    langgraph_resident,
    routine_post_runtime,
    world_character_contracts,
)
from app.runtime.characters import management as agent_service
from app.services import community as community_service
from app.services.agent_activity_policy import ActivityPolicy
from app.services.direct_llm import DirectLlmCallContext, DirectLlmError
from app.services.resident_contracts import LangGraphResidentContext
from app.services.routine_post_context import (
    RoutineInteractionInput,
    assemble_routine_post_context,
)
from app.services.routine_post_planner import (
    GEMINI_ROUTINE_BEAT_PLAN_RESPONSE_SCHEMA,
    GEMINI_ROUTINE_POST_DRAFT_RESPONSE_SCHEMA,
    RoutineGeneration,
    allowed_continuity_facts,
    build_routine_beat_plan_response_schema,
)

DAYPARTS = ("dawn", "morning", "afternoon", "evening")


@pytest.mark.parametrize(
    "response_schema",
    (
        GEMINI_ROUTINE_BEAT_PLAN_RESPONSE_SCHEMA,
        GEMINI_ROUTINE_POST_DRAFT_RESPONSE_SCHEMA,
    ),
)
def test_routine_gemini_transport_uses_json_schema_without_openapi_extras(
    response_schema: dict[str, object],
) -> None:
    def assert_supported(value: object) -> None:
        if isinstance(value, dict):
            assert "additionalProperties" not in value
            assert "additional_properties" not in value
            assert "$defs" not in value
            assert "$ref" not in value
            for item in value.values():
                assert_supported(item)
        elif isinstance(value, list):
            for item in value:
                assert_supported(item)

    config = build_generate_content_config(
        model="gemini-3.1-flash-lite",
        system_prompt="system",
        max_output_tokens=2_400,
        response_mime_type="application/json",
        response_schema=response_schema,
        thinking_level="medium",
    )
    serialized = config.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert "responseSchema" not in serialized
    assert serialized["responseJsonSchema"] == response_schema
    assert_supported(serialized["responseJsonSchema"])


def test_routine_planner_schema_binds_continuation_to_server_evidence() -> None:
    continuity_facts = [
        "previous_beat_id:beat-1",
        "previous_post_id:post-1",
        "previous_sequence_no:1",
    ]
    event_ids = ["event-1", "event-2"]
    detail_keys = [
        "previous_success.post.title",
        "source_events.event-1",
    ]

    response_schema = build_routine_beat_plan_response_schema(
        has_previous_success=True,
        continuity_facts=continuity_facts,
        considered_source_event_ids=event_ids,
        detail_keys=detail_keys,
    )
    properties = response_schema["properties"]

    assert properties["scene_kind"]["enum"] == ["continue", "conclude"]
    assert properties["continuity_facts"] == {
        "type": "array",
        "items": {"type": "string", "enum": continuity_facts},
        "minItems": 1,
        "maxItems": 3,
    }
    assert properties["considered_source_event_ids"] == {
        "type": "array",
        "items": {"type": "string", "enum": event_ids},
        "minItems": 2,
        "maxItems": 2,
    }
    assert properties["used_source_event_ids"]["items"]["enum"] == event_ids
    assert properties["used_detail_keys"]["items"]["enum"] == detail_keys
    assert (
        properties["source_event_effects"]["items"]["properties"]["source_event_id"][
            "enum"
        ]
        == event_ids
    )

    config = build_generate_content_config(
        model="gemini-3.1-flash-lite",
        system_prompt="system",
        max_output_tokens=2_400,
        response_mime_type="application/json",
        response_schema=response_schema,
        thinking_level="medium",
    )
    serialized = config.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert "responseSchema" not in serialized
    assert serialized["responseJsonSchema"] == response_schema


def test_routine_planner_schema_disallows_evidence_without_prior_success() -> None:
    response_schema = build_routine_beat_plan_response_schema(
        has_previous_success=False,
        continuity_facts=[],
        considered_source_event_ids=[],
        detail_keys=[],
    )
    properties = response_schema["properties"]

    assert properties["scene_kind"]["enum"] == ["start"]
    assert properties["continuity_facts"]["minItems"] == 0
    assert properties["continuity_facts"]["maxItems"] == 0
    assert properties["considered_source_event_ids"]["minItems"] == 0
    assert properties["considered_source_event_ids"]["maxItems"] == 0
    assert properties["used_source_event_ids"]["maxItems"] == 0
    assert properties["used_detail_keys"]["maxItems"] == 0
    assert properties["source_event_effects"]["maxItems"] == 0


@dataclass(frozen=True)
class RoutineFixture:
    user: models.User
    character: models.Character
    credential: models.LlmCredential
    world: models.World
    world_character: models.WorldCharacter
    plan: models.DailyActivityPlan
    morning_episode: models.ActivityEpisode


class StaticInteractionSource:
    def __init__(self, events: list[RoutineInteractionInput]) -> None:
        self.events = events

    def candidates(self, *_args, **_kwargs) -> list[RoutineInteractionInput]:
        return list(self.events)


class FakeRoutineProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        *,
        resident_context: LangGraphResidentContext,
        routine_context,
        beat: models.ActivityBeat,
        tracker,
    ) -> RoutineGeneration:
        self.calls += 1
        for node in ("RoutineBeatPlanner", "PostWriter"):
            call_order = tracker.next_call_order()
            provider_order = tracker.next_provider_call_order()
            tracker.record_call(
                context=DirectLlmCallContext(
                    credential_id=resident_context.credential.id,
                    character_id=resident_context.character.id,
                    agent_run_id=resident_context.run_id,
                    node=node,
                    lane=node.lower(),
                    provider=resident_context.credential.provider,
                    model=resident_context.credential.model,
                    key_fingerprint=resident_context.credential.key_fingerprint,
                ),
                call_order=call_order,
                provider_call_order=provider_order,
                status="succeeded",
                duration_ms=5,
            )
        used_ids = routine_context.considered_source_event_ids[:1]
        effects = [
            schemas.RoutineSourceEventEffect(
                source_event_id=event_id,
                effect="acknowledge",
                intensity=8,
                state_change=schemas.RoutineStateChange(
                    mood="curious",
                    mood_intensity_delta=8,
                ),
            )
            for event_id in used_ids
        ]
        plan = schemas.RoutineBeatPlan(
            episode_id=routine_context.episode.id,
            beat_id=beat.id,
            sequence_no=beat.sequence_no,
            scene_kind="start" if beat.sequence_no == 1 else "continue",
            scene_brief=(
                "Begin the selected morning activity."
                if beat.sequence_no == 1
                else "Continue the same activity after considering the response."
            ),
            continuity_facts=(
                []
                if beat.sequence_no == 1
                else allowed_continuity_facts(routine_context)
            ),
            considered_source_event_ids=routine_context.considered_source_event_ids,
            used_source_event_ids=used_ids,
            used_detail_keys=[],
            source_event_effects=effects,
        )
        state_after = activity_state_contracts.apply_state_changes(
            routine_context.state_before,
            [effect.state_change.model_dump() for effect in effects],
            scheduled_without_source=not bool(used_ids),
        )
        return RoutineGeneration(
            plan=plan,
            draft=schemas.RoutinePostDraft(
                title=f"Morning activity scene {beat.sequence_no}",
                body=(
                    "The academy morning activity begins."
                    if beat.sequence_no == 1
                    else "The same activity continues with a new observation."
                ),
                topic_signature=f"morning-scene-{beat.sequence_no}",
                novelty_basis="The current activity state and prior successful scene.",
            ),
            state_after=state_after,
        )


class TransientFailureProvider:
    async def generate(self, **_kwargs) -> RoutineGeneration:
        raise DirectLlmError("temporary provider timeout")


class InventedEvidenceProvider(FakeRoutineProvider):
    async def generate(self, **kwargs) -> RoutineGeneration:
        generation = await super().generate(**kwargs)
        generation.plan.used_detail_keys = ["private.unverified.detail"]
        return generation


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


def _utc(local_value: datetime) -> datetime:
    return local_value.replace(tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)


def _seed(db: Session, *, autonomous_enabled: bool = True) -> RoutineFixture:
    now = _utc(datetime(2026, 8, 10, 9, 0))
    user = models.User(
        id="user-routine",
        email="routine@example.test",
        display_name="Routine owner",
        display_name_normalized="routine owner",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )
    character = models.Character(
        id="character-routine",
        owner_id=user.id,
        name="Mira",
        handle="mira-routine",
        one_liner="An observant magic academy student",
        personality="Careful, curious, and warm.",
        speech_style="Calm and considerate.",
        worldview="Learning deepens through cooperation.",
        topic_preferences="Alchemy, runes, and friends",
        safety_rules="Never use dangerous spells alone.",
        persona_summary="A second-year alchemy student at Arcana Academy.",
        moderation_status="active",
    )
    credential = models.LlmCredential(
        id="credential-routine",
        owner_id=user.id,
        character_id=character.id,
        provider="google",
        purpose="agent",
        model="gemini-test",
        auth_profile_id="profile-routine",
        label="Routine test key",
        encrypted_api_key="not-used-by-fake-provider",
        key_fingerprint="fixture-key",
        enabled=True,
    )
    world = models.World(
        id="world-routine",
        slug="arcana-routine",
        owner_user_id=user.id,
        name="Arcana Academy",
        tagline="A residential school of practical magic",
        setting_description="Students learn magic through classes and clubs.",
        daily_life_description="Classes, meals, practice, and friendship shape each day.",
        genre_tags=["fantasy"],
        tone_tags=["warm"],
        timezone="Asia/Seoul",
        language="ko",
        visibility="public",
        join_policy="open",
        status="published",
        contract_version="world-v1",
        contract_hash="b" * 64,
        readiness_status="publish_ready",
        create_idempotency_key="create-world-routine",
    )
    membership = models.WorldMembership(
        id="membership-routine",
        world_id=world.id,
        user_id=user.id,
        role="member",
        status="active",
        joined_at=now,
    )
    character_contract_hash = world_character_contracts.character_contract_hash(
        character
    )
    world_character = models.WorldCharacter(
        id="world-character-routine",
        world_id=world.id,
        character_id=character.id,
        membership_id=membership.id,
        role_key="student",
        status="active",
        autonomous_enabled=autonomous_enabled,
        activity_runtime_mode="routine_resident_v1",
        local_profile={"background": "second-year alchemy student"},
        character_contract_hash=character_contract_hash,
        world_contract_hash=world.contract_hash,
    )
    profile = models.WorldCommunityProfile(
        id="profile-routine",
        world_character_id=world_character.id,
        status="ready",
        visible_summary="A careful academy student.",
        core_interests=["alchemy"],
        adjacent_interests=["library"],
        avoid_topics=["dangerous magic"],
        discovery_openness=70,
        search_keywords=["alchemy"],
        action_profile={},
        schema_version=1,
        generator_version="test-v1",
        character_contract_hash=world_character.character_contract_hash,
        world_contract_hash=world.contract_hash,
        provider="google",
        model="gemini-test",
        credential_id=credential.id,
        generated_at=now,
        approved_at=now,
    )
    repertoire = models.WorldActivityRepertoire(
        id="repertoire-routine",
        world_character_id=world_character.id,
        status="ready",
        schema_version=1,
        generator_version="test-v1",
        character_contract_hash=world_character.character_contract_hash,
        world_contract_hash=world.contract_hash,
        community_profile_id=profile.id,
        provider="google",
        model="gemini-test",
        credential_id=credential.id,
        validation_summary={"candidate_count": 40},
        generated_at=now,
        approved_at=now,
    )
    db.add_all([user, character, credential, world])
    db.flush()
    db.add(membership)
    db.flush()
    db.add(world_character)
    db.flush()
    db.add_all(
        [
            models.CharacterActiveWorld(
                character_id=character.id,
                world_character_id=world_character.id,
                selected_at=now,
                idempotency_key="active-world-routine",
                version=1,
            ),
            profile,
        ]
    )
    db.flush()
    db.add(repertoire)
    db.flush()

    plan = models.DailyActivityPlan(
        id="plan-routine",
        world_id=world.id,
        world_character_id=world_character.id,
        local_date=date(2026, 8, 10),
        timezone_name=world.timezone,
        timezone_contract_version="world-local-daypart-v1",
        repertoire_id=repertoire.id,
        world_definition_hash=world.contract_hash,
        character_definition_hash=world_character.character_contract_hash,
        repertoire_contract_version="test-v1",
        selection_contract_version="daily-selection-v1",
        selection_seed_hash="d" * 64,
        status="planned",
        version=1,
    )
    db.add(plan)
    db.flush()
    windows = {
        "dawn": (0, 6),
        "morning": (6, 12),
        "afternoon": (12, 18),
        "evening": (18, 24),
    }
    morning_episode: models.ActivityEpisode | None = None
    for daypart in DAYPARTS:
        selected_candidate: models.WorldActivityCandidate | None = None
        for candidate_ordinal in range(1, 11):
            candidate = models.WorldActivityCandidate(
                id=f"candidate-{daypart}-{candidate_ordinal}",
                repertoire_id=repertoire.id,
                daypart=daypart,
                ordinal=candidate_ordinal,
                activity_kind="duty",
                title=f"{daypart} academy practice {candidate_ordinal}",
                activity_seed=(
                    f"Continue the {daypart} academy practice "
                    f"variation {candidate_ordinal}."
                ),
                social_mode="open_to_interaction",
                canonical_signature=sha256(
                    f"{daypart}:{candidate_ordinal}".encode()
                ).hexdigest(),
                enabled=True,
            )
            db.add(candidate)
            if candidate_ordinal == 1:
                selected_candidate = candidate
        db.flush()
        assert selected_candidate is not None
        start_hour, end_hour = windows[daypart]
        start_local = datetime(2026, 8, 10, start_hour, 0)
        end_local = (
            datetime(2026, 8, 11, 0, 0)
            if end_hour == 24
            else datetime(2026, 8, 10, end_hour, 0)
        )
        item = models.DailyActivityPlanItem(
            id=f"item-{daypart}",
            plan_id=plan.id,
            world_id=world.id,
            world_character_id=world_character.id,
            daypart=daypart,
            selected_candidate_id=selected_candidate.id,
            candidate_signature=selected_candidate.canonical_signature,
            candidate_ordinal=selected_candidate.ordinal,
            activity_kind=selected_candidate.activity_kind,
            title=selected_candidate.title,
            activity_seed=selected_candidate.activity_seed,
            social_mode=selected_candidate.social_mode,
            scheduled_start_at=_utc(start_local),
            scheduled_end_at=_utc(end_local),
            status="planned",
            version=1,
        )
        db.add(item)
        db.flush()
        episode = models.ActivityEpisode(
            id=f"episode-{daypart}",
            world_id=world.id,
            world_character_id=world_character.id,
            plan_item_id=item.id,
            effective_activity_snapshot={
                "title": item.title,
                "activity_seed": item.activity_seed,
            },
            status="planned",
            current_state_schema_version=1,
            current_state_snapshot=activity_state_contracts.initial_state(),
            next_sequence_no=1,
            version=1,
        )
        db.add(episode)
        if daypart == "morning":
            morning_episode = episode
    db.commit()
    assert morning_episode is not None
    return RoutineFixture(
        user=user,
        character=character,
        credential=credential,
        world=world,
        world_character=world_character,
        plan=plan,
        morning_episode=morning_episode,
    )


def test_world_profile_readiness_replaces_legacy_tendency_gate() -> None:
    engine = _engine()
    with Session(engine) as db:
        fixture = _seed(db)
        setting = agent_crud.ensure_setting(db, fixture.character.id)

        assert not agent_service._has_tendency_analysis(setting)

        readiness = agent_service._activity_profile_readiness(
            db,
            character=fixture.character,
            setting=setting,
        )

        assert readiness.ready
        assert readiness.source == "world_community_profile"
        assert readiness.reason_code is None
        assert readiness.world_id == fixture.world.id
        assert readiness.world_character_id == fixture.world_character.id
        agent_service._ensure_activity_profile_ready(
            db,
            character=fixture.character,
            setting=setting,
        )


def test_world_profile_readiness_rejects_incomplete_repertoire() -> None:
    engine = _engine()
    with Session(engine) as db:
        fixture = _seed(db)
        setting = agent_crud.ensure_setting(db, fixture.character.id)
        candidate = db.get(models.WorldActivityCandidate, "candidate-morning-10")
        assert candidate is not None
        candidate.enabled = False
        db.commit()

        readiness = agent_service._activity_profile_readiness(
            db,
            character=fixture.character,
            setting=setting,
        )

        assert not readiness.ready
        assert readiness.source == "world_community_profile"
        assert readiness.reason_code == "world_activity_repertoire_not_ready"
        with pytest.raises(agent_service.ActivityProfileRequiredError):
            agent_service._ensure_activity_profile_ready(
                db,
                character=fixture.character,
                setting=setting,
            )


def test_legacy_runtime_still_requires_legacy_tendency_analysis() -> None:
    engine = _engine()
    with Session(engine) as db:
        fixture = _seed(db)
        setting = agent_crud.ensure_setting(db, fixture.character.id)
        fixture.world_character.activity_runtime_mode = "legacy_resident_v1"
        db.commit()

        readiness = agent_service._activity_profile_readiness(
            db,
            character=fixture.character,
            setting=setting,
        )

        assert not readiness.ready
        assert readiness.source == "legacy_tendency"
        assert readiness.reason_code == "legacy_tendency_not_ready"
        with pytest.raises(agent_service.TendencyAnalysisRequiredError):
            agent_service._ensure_activity_profile_ready(
                db,
                character=fixture.character,
                setting=setting,
            )


def _resident_context(
    db: Session,
    fixture: RoutineFixture,
    *,
    run_id: str,
    now: datetime,
) -> LangGraphResidentContext:
    for active_run in db.scalars(
        select(models.AgentRun).where(models.AgentRun.status == "running")
    ):
        active_run.status = "completed"
        active_run.completed_at = now
    session_key = f"routine-test:{run_id}"
    db.add(
        models.AgentRun(
            id=run_id,
            user_id=fixture.user.id,
            character_id=fixture.character.id,
            credential_id=fixture.credential.id,
            agent_id="agent-routine",
            session_key=session_key,
            status="running",
            created_at=now,
        )
    )
    db.commit()
    return LangGraphResidentContext(
        db=db,
        run_id=run_id,
        user_id=fixture.user.id,
        agent_id="agent-routine",
        session_key=session_key,
        character=fixture.character,
        credential=fixture.credential,
        state=None,
        activity_policy=ActivityPolicy(
            within_active_hours=True,
            allowed_actions=("post",),
            blocked_reasons={},
            next_tick_at=now + timedelta(hours=1),
            summary="allowed=post",
        ),
        selected_post_id=None,
        run_started_at=now,
    )


def test_context_bounds_events_and_excludes_cross_world_input() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 10, 10, 5))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        events = [
            RoutineInteractionInput(
                source_event_id=f"event-{index:02d}",
                world_id=fixture.world.id,
                consumer_world_character_id=fixture.world_character.id,
                actor_world_character_id=f"actor-{index:02d}",
                excerpt=f"Comment {index}",
                occurred_at=now - timedelta(minutes=index),
                directness=100 - index,
                episode_relevance=80,
                relationship_band="familiar",
            )
            for index in range(1, 13)
        ]
        events.append(
            RoutineInteractionInput(
                source_event_id="cross-world",
                world_id="world-other",
                consumer_world_character_id=fixture.world_character.id,
                actor_world_character_id="actor-other",
                excerpt="This must never enter the prompt.",
                occurred_at=now - timedelta(minutes=1),
            )
        )
        context = assemble_routine_post_context(
            db,
            world_character=fixture.world_character,
            character=fixture.character,
            now=now,
            interaction_source=StaticInteractionSource(events),
        )

        assert len(context.source_events) == 8
        assert context.considered_source_event_ids == [
            f"event-{index:02d}" for index in range(1, 9)
        ]
        assert context.eligible_event_count == 12
        assert context.overflow_reason_counts == {
            "world_scope_filtered": 1,
            "prompt_item_limit": 4,
        }
        assert "cross-world" not in context.considered_source_event_ids


def test_routine_runtime_publishes_scoped_continuous_posts_and_consumes_event_once() -> (
    None
):
    engine = _engine()
    first_now = _utc(datetime(2026, 8, 10, 10, 5))
    second_now = _utc(datetime(2026, 8, 10, 11, 5))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        friend_character = models.Character(
            id="character-routine-friend",
            owner_id=fixture.user.id,
            name="Sage",
            handle="sage-routine",
            one_liner="A practical academy classmate",
            personality="Supportive and direct.",
            speech_style="Friendly and concise.",
            worldview="Friends improve by sharing observations.",
            topic_preferences="Alchemy and study groups",
            safety_rules="Avoid unsafe experiments.",
            persona_summary="Mira's academy classmate.",
            moderation_status="active",
        )
        db.add(friend_character)
        db.flush()
        friend_world_character = models.WorldCharacter(
            id="world-character-friend",
            world_id=fixture.world.id,
            character_id=friend_character.id,
            membership_id=fixture.world_character.membership_id,
            status="active",
            character_contract_hash=world_character_contracts.character_contract_hash(
                friend_character
            ),
            world_contract_hash=fixture.world.contract_hash,
        )
        db.add(friend_world_character)
        db.flush()
        provider = FakeRoutineProvider()
        first = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(db, fixture, run_id="run-first", now=first_now),
                provider=provider,
            )
        )
        target_post_id = first["publish_result"]["post_id"]
        source_reply = models.Post(
            id="post-reply-1",
            author_character_id=friend_character.id,
            world_id=fixture.world.id,
            author_world_character_id=friend_world_character.id,
            reply_to_post_id=target_post_id,
            post_type="reply",
            visibility="public",
            author_name=friend_character.name,
            title="Re: routine",
            body="Try lowering the potion heat on the next pass.",
            search_document="Try lowering the potion heat on the next pass.",
            created_at=_utc(datetime(2026, 8, 10, 10, 30)),
        )
        db.add(source_reply)
        db.flush()
        source_event = models.SocialEvent(
            id="event-reply-1",
            world_id=fixture.world.id,
            actor_world_character_id=friend_world_character.id,
            target_world_character_id=fixture.world_character.id,
            event_type="comment_created",
            result="succeeded",
            occurred_at=_utc(datetime(2026, 8, 10, 10, 30)),
            idempotency_key="fixture:event-reply-1",
            schema_version="social-event-v1",
        )
        db.add(source_event)
        db.flush()
        db.add(
            models.SocialEventEvidence(
                id="evidence-reply-1",
                social_event_id=source_event.id,
                evidence_kind="reply_post",
                source_object_type="post",
                source_object_id=source_reply.id,
                root_post_id=target_post_id,
                source_post_id=source_reply.id,
                target_post_id=target_post_id,
                source_visibility_at_event="public",
                source_author_id_at_event=friend_world_character.id,
                occurred_at=source_event.occurred_at,
            )
        )
        db.commit()
        event_source = StaticInteractionSource(
            [
                RoutineInteractionInput(
                    source_event_id="event-reply-1",
                    world_id=fixture.world.id,
                    consumer_world_character_id=fixture.world_character.id,
                    actor_world_character_id="world-character-friend",
                    excerpt="Try lowering the potion heat on the next pass.",
                    occurred_at=_utc(datetime(2026, 8, 10, 10, 30)),
                    directness=100,
                    episode_relevance=100,
                    relationship_band="close",
                )
            ]
        )
        second = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(db, fixture, run_id="run-second", now=second_now),
                interaction_source=event_source,
                provider=provider,
            )
        )

        posts = list(db.scalars(select(models.Post).order_by(models.Post.created_at)))
        beats = list(
            db.scalars(
                select(models.ActivityBeat)
                .where(models.ActivityBeat.episode_id == fixture.morning_episode.id)
                .order_by(models.ActivityBeat.sequence_no)
            )
        )
        consumption = db.scalar(select(models.ActivityEventConsumption))
        post_events = list(
            db.scalars(
                select(models.SocialEvent)
                .where(models.SocialEvent.event_type == "post_published")
                .order_by(models.SocialEvent.occurred_at)
            )
        )

        assert first["routine_outcome"] == "POST_SUCCEEDED"
        assert second["routine_outcome"] == "POST_SUCCEEDED"
        assert first["llm_usage_summary"]["provider_call_count"] == 2
        assert second["llm_usage_summary"]["provider_call_count"] == 2
        assert provider.calls == 2
        assert len(posts) == 3
        assert len(beats) == 2
        assert [beat.sequence_no for beat in beats] == [1, 2]
        assert all(post.world_id == fixture.world.id for post in posts)
        routine_posts = [
            post
            for post in posts
            if post.author_world_character_id == fixture.world_character.id
        ]
        assert len(routine_posts) == 2
        assert all(
            post.author_world_character_id == fixture.world_character.id
            for post in routine_posts
        )
        assert beats[0].source_post_id == routine_posts[0].id
        assert beats[1].previous_successful_beat_id == beats[0].id
        assert len(post_events) == 2
        assert all(event.world_id == fixture.world.id for event in post_events)
        assert all(
            event.actor_world_character_id == fixture.world_character.id
            and event.target_world_character_id is None
            for event in post_events
        )
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 3
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 3
        assert beats[1].source_post_id == routine_posts[1].id
        assert beats[1].result_snapshot["used_source_event_ids"] == ["event-reply-1"]
        assert consumption is not None
        assert consumption.status == "applied"
        assert consumption.source_social_event_id == "event-reply-1"
        assert fixture.morning_episode.last_successful_beat_id == beats[1].id
        assert fixture.morning_episode.next_sequence_no == 3

        no_due_provider = FakeRoutineProvider()
        no_due = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(
                    db,
                    fixture,
                    run_id="run-no-due",
                    now=_utc(datetime(2026, 8, 10, 11, 20)),
                ),
                interaction_source=event_source,
                provider=no_due_provider,
            )
        )
        assert no_due["routine_outcome"] == "BEAT_NOT_DUE"
        assert no_due_provider.calls == 0
        assert db.scalar(select(func.count(models.Post.id))) == 3


def test_owner_manual_reply_is_observed_once_on_next_allowed_beat() -> None:
    engine = _engine()
    first_now = _utc(datetime(2026, 8, 10, 10, 5))
    reply_now = _utc(datetime(2026, 8, 10, 10, 30))
    second_now = _utc(datetime(2026, 8, 10, 11, 5))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        provider = FakeRoutineProvider()
        first = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(
                    db, fixture, run_id="manual-inbox-first", now=first_now
                ),
                provider=provider,
            )
        )
        assert first["routine_outcome"] == "POST_SUCCEEDED"
        target_post_id = first["publish_result"]["post_id"]

        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="manual-inbox-installation",
                owner_user_id=fixture.user.id,
                bootstrap_state="claimed",
                local_label="fixture",
                claimed_at=first_now,
            )
        )
        membership = db.get(
            models.WorldMembership, fixture.world_character.membership_id
        )
        assert membership is not None
        membership.role = "owner"

        owner_character = models.Character(
            id="character-owner-manual-inbox",
            owner_id=fixture.user.id,
            name="Owner Bird",
            handle="owner-manual-inbox",
            one_liner="The user's direct voice in this World.",
            personality="Direct and kind.",
            speech_style="Brief.",
            worldview="Friends listen to one another.",
            topic_preferences="Academy life",
            safety_rules="Stay safe.",
            persona_summary="Owner controlled fixture.",
            moderation_status="active",
            execution_mode="local",
        )
        db.add(owner_character)
        db.flush()
        owner_world_character = models.WorldCharacter(
            id="world-character-owner-manual-inbox",
            world_id=fixture.world.id,
            character_id=owner_character.id,
            membership_id=fixture.world_character.membership_id,
            role_key="student",
            status="active",
            control_mode="owner_controlled",
            owner_user_id=fixture.user.id,
            autonomous_enabled=False,
            activity_runtime_mode="legacy_resident_v1",
            feed_runtime_mode="legacy_latest_v1",
            local_profile={"display_name": "Owner Bird"},
            character_contract_hash=world_character_contracts.character_contract_hash(
                owner_character
            ),
            world_contract_hash=fixture.world.contract_hash,
        )
        db.add(owner_world_character)
        db.flush()
        db.add(
            models.CharacterActiveWorld(
                character_id=owner_character.id,
                world_character_id=owner_world_character.id,
                selected_at=reply_now,
                idempotency_key="owner-manual-inbox-active-world",
                version=1,
            )
        )
        db.commit()

        manual_reply = create_owner_reply(
            SqlAlchemySocialWriteUnitOfWork(db),
            OwnerReplyCommand(
                world_id=fixture.world.id,
                target_post_id=target_post_id,
                current_user_id=fixture.user.id,
                idempotency_key="owner-manual-inbox-reply",
                body="다음 실험에서는 온도를 조금 낮춰 보는 건 어때?"
            ),
        )
        assert manual_reply.delivery.provider_call_count == 0
        assert manual_reply.delivery.inbox_status == "pending"
        candidate = db.get(
            models.OwnerManualInboxCandidate,
            manual_reply.delivery.inbox_candidate_id,
        )
        assert candidate is not None
        candidate.created_at = reply_now
        db.commit()

        second = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(
                    db, fixture, run_id="manual-inbox-second", now=second_now
                ),
                provider=provider,
            )
        )

        db.refresh(candidate)
        beats = list(
            db.scalars(
                select(models.ActivityBeat)
                .where(models.ActivityBeat.episode_id == fixture.morning_episode.id)
                .order_by(models.ActivityBeat.sequence_no)
            )
        )
        posts = list(db.scalars(select(models.Post).order_by(models.Post.created_at)))
        manual_source_id = f"manual-inbox:{candidate.id}"

        assert second["routine_outcome"] == "POST_SUCCEEDED"
        assert second["llm_usage_summary"]["provider_call_count"] == 2
        assert provider.calls == 2
        assert len(beats) == 2
        assert manual_source_id in beats[1].result_snapshot["used_source_event_ids"]
        assert beats[1].result_snapshot["considered_source_event_ids"] == [
            manual_source_id
        ]
        assert candidate.status == "consumed"
        assert candidate.target_activity_beat_id == beats[1].id
        assert candidate.consumed_at is not None
        assert db.scalar(select(func.count(models.ActivityEventConsumption.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 1
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 1
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 3
        assert len(posts) == 3
        assert sum(post.reply_to_post_id is not None for post in posts) == 1
        assert all(
            post.reply_to_post_id is None
            for post in posts
            if post.author_world_character_id == fixture.world_character.id
        )

        no_due_provider = FakeRoutineProvider()
        no_due = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(
                    db,
                    fixture,
                    run_id="manual-inbox-no-due",
                    now=_utc(datetime(2026, 8, 10, 11, 20)),
                ),
                provider=no_due_provider,
            )
        )
        assert no_due["routine_outcome"] == "BEAT_NOT_DUE"
        assert no_due_provider.calls == 0
        assert db.scalar(select(func.count(models.Post.id))) == 3


def test_runtime_closes_elapsed_episode_before_activating_current_daypart() -> None:
    engine = _engine()
    morning_now = _utc(datetime(2026, 8, 10, 10, 5))
    afternoon_now = _utc(datetime(2026, 8, 10, 16, 5))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        provider = FakeRoutineProvider()

        first = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(
                    db,
                    fixture,
                    run_id="run-morning-before-pause",
                    now=morning_now,
                ),
                provider=provider,
            )
        )
        morning_post_id = first["publish_result"]["post_id"]
        morning_item = db.get(models.DailyActivityPlanItem, "item-morning")
        assert first["routine_outcome"] == "POST_SUCCEEDED"
        assert morning_item is not None and morning_item.status == "active"
        assert fixture.morning_episode.status == "active"

        second = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(
                    db,
                    fixture,
                    run_id="run-afternoon-after-resume",
                    now=afternoon_now,
                ),
                provider=provider,
            )
        )

        db.refresh(fixture.morning_episode)
        db.refresh(morning_item)
        dawn_item = db.get(models.DailyActivityPlanItem, "item-dawn")
        dawn_episode = db.get(models.ActivityEpisode, "episode-dawn")
        afternoon_item = db.get(models.DailyActivityPlanItem, "item-afternoon")
        afternoon_episode = db.get(models.ActivityEpisode, "episode-afternoon")

        assert second["routine_outcome"] == "POST_SUCCEEDED"
        assert morning_item.status == "completed"
        assert morning_item.terminal_reason_code == "daypart_completed"
        assert fixture.morning_episode.status == "completed"
        assert fixture.morning_episode.terminal_reason_code == "daypart_completed"
        assert fixture.morning_episode.completion_summary == {
            "successful_beat_count": 1,
            "successful_post_ids": [morning_post_id],
        }
        assert dawn_item is not None and dawn_item.status == "skipped"
        assert dawn_item.terminal_reason_code == "daypart_window_elapsed"
        assert dawn_episode is not None and dawn_episode.status == "cancelled"
        assert afternoon_item is not None and afternoon_item.status == "active"
        assert afternoon_episode is not None and afternoon_episode.status == "active"
        assert provider.calls == 2
        assert db.scalar(select(func.count(models.Post.id))) == 2
        assert (
            db.scalar(
                select(func.count(models.ActivityBeat.id)).where(
                    models.ActivityBeat.episode_id == "episode-dawn"
                )
            )
            == 0
        )


def test_transient_provider_failure_retries_same_beat_without_duplicate_post() -> None:
    engine = _engine()
    first_now = _utc(datetime(2026, 8, 10, 10, 5))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        failed = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(db, fixture, run_id="run-timeout", now=first_now),
                provider=TransientFailureProvider(),
            )
        )
        pending = db.scalar(select(models.ActivityBeat))
        assert failed["routine_outcome"] == "provider_transient"
        assert pending is not None
        assert pending.status == "pending"
        assert pending.attempt_count == 1

        succeeded = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(
                    db,
                    fixture,
                    run_id="run-retry",
                    now=first_now + timedelta(minutes=1),
                ),
                provider=FakeRoutineProvider(),
            )
        )
        retried = db.scalar(select(models.ActivityBeat))
        assert succeeded["routine_outcome"] == "POST_SUCCEEDED"
        assert retried is not None
        assert retried.id == pending.id
        assert retried.status == "succeeded"
        assert retried.attempt_count == 2
        assert db.scalar(select(func.count(models.ActivityBeat.id))) == 1
        assert db.scalar(select(func.count(models.Post.id))) == 1


def test_provider_adapter_cannot_bypass_server_evidence_validation() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 10, 10, 5))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        result = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(db, fixture, run_id="run-invented-evidence", now=now),
                provider=InventedEvidenceProvider(),
            )
        )
        beat = db.scalar(select(models.ActivityBeat))

        assert result["routine_outcome"] == "routine_generation_failed"
        assert beat is not None
        assert beat.status == "failed"
        assert beat.source_post_id is None
        assert db.scalar(select(func.count(models.Post.id))) == 0


def test_publish_fault_rolls_back_post_state_and_execution(monkeypatch) -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 10, 10, 5))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        initial_state = dict(fixture.morning_episode.current_state_snapshot)
        original_create = routine_post_runtime.community_service.create_agent_tool_post

        def create_then_fail(*args, **kwargs):
            original_create(*args, **kwargs)
            raise community_service.CommunityServiceError("fault after post flush")

        monkeypatch.setattr(
            routine_post_runtime.community_service,
            "create_agent_tool_post",
            create_then_fail,
        )
        result = asyncio.run(
            routine_post_runtime.run_routine_post_runtime(
                _resident_context(db, fixture, run_id="run-fault", now=now),
                provider=FakeRoutineProvider(),
            )
        )
        beat = db.scalar(select(models.ActivityBeat))
        db.refresh(fixture.morning_episode)

        assert result["routine_outcome"] == "publish_transaction_failed"
        assert beat is not None
        assert beat.status == "failed"
        assert beat.source_post_id is None
        assert beat.state_after_snapshot is None
        assert fixture.morning_episode.last_successful_beat_id is None
        assert fixture.morning_episode.current_state_snapshot == initial_state
        assert db.scalar(select(func.count(models.Post.id))) == 0
        assert db.scalar(select(func.count(models.AgentPublicActionExecution.id))) == 0
        assert db.scalar(select(func.count(models.AgentActivityLog.id))) == 0


def test_runtime_mode_readiness_does_not_enable_autonomy() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 10, 10, 5))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db, autonomous_enabled=False)
        fixture.world_character.activity_runtime_mode = "legacy_resident_v1"
        db.commit()

        updated = daily_activity_plans.update_activity_runtime_mode(
            db,
            character_id=fixture.character.id,
            world_id=fixture.world.id,
            user=fixture.user,
            data=schemas.WorldCharacterRuntimeModeUpdate(
                activity_runtime_mode="routine_resident_v1"
            ),
            now=now,
        )

        assert updated.activity_runtime_mode == "routine_resident_v1"
        assert updated.autonomous_enabled is False
        assert fixture.world_character.activity_runtime_mode == "routine_resident_v1"
        assert fixture.world_character.autonomous_enabled is False


def test_langgraph_routes_routine_mode_without_building_legacy_graph(
    monkeypatch,
) -> None:
    context = SimpleNamespace(
        db=object(),
        character=SimpleNamespace(id="character-routine"),
    )
    monkeypatch.setattr(
        langgraph_resident,
        "routine_world_character_for_character",
        lambda *_args, **_kwargs: SimpleNamespace(id="world-character-routine"),
    )
    monkeypatch.setattr(
        langgraph_resident.agent_activity_policy,
        "is_imported_world_runtime_locked",
        lambda *_args, **_kwargs: False,
    )

    async def fake_routine(_context):
        return {"engine": "routine_resident_v1", "status": "completed"}

    def legacy_graph_must_not_run(*_args, **_kwargs):
        raise AssertionError("legacy graph must not run for routine mode")

    monkeypatch.setattr(langgraph_resident, "run_routine_post_runtime", fake_routine)
    monkeypatch.setattr(langgraph_resident, "_build_graph", legacy_graph_must_not_run)

    result = asyncio.run(langgraph_resident.run_resident_langgraph(context))
    assert result == {"engine": "routine_resident_v1", "status": "completed"}


def test_langgraph_composes_keyword_feed_only_for_explicit_feed_mode(
    monkeypatch,
) -> None:
    context = SimpleNamespace(
        db=object(),
        character=SimpleNamespace(id="character-keyword-feed"),
    )
    monkeypatch.setattr(
        langgraph_resident,
        "routine_world_character_for_character",
        lambda *_args, **_kwargs: SimpleNamespace(
            id="world-character-keyword-feed",
            feed_runtime_mode="keyword_search_v1",
        ),
    )
    monkeypatch.setattr(
        langgraph_resident.agent_activity_policy,
        "is_imported_world_runtime_locked",
        lambda *_args, **_kwargs: False,
    )

    call_order: list[str] = []

    async def fake_inbox(_context):
        call_order.append("inbox")
        return {
            "engine": "inbox_lane_v1",
            "status": "completed",
            "outcome": "INBOX_ACTION_SUCCEEDED",
            "publish_result": {
                "public_action_count": 1,
                "target_post_id": "post-unread-reply",
            },
            "llm_usage_summary": {"provider_call_count": 2},
        }

    async def fake_routine(_context):
        call_order.append("routine")
        return {
            "engine": "routine_resident_v1",
            "status": "observed",
            "publish_result": {"public_action_count": 0},
            "llm_usage_summary": {"provider_call_count": 0},
        }

    async def fake_feed(_context):
        call_order.append("feed")
        return {
            "engine": "keyword_search_v1",
            "status": "observed",
            "publish_result": {"public_action_count": 0},
            "llm_usage_summary": {"provider_call_count": 0},
        }

    monkeypatch.setattr(langgraph_resident, "run_routine_post_runtime", fake_routine)
    monkeypatch.setattr(langgraph_resident, "_run_combined_inbox_lane", fake_inbox)
    monkeypatch.setattr(langgraph_resident, "run_world_keyword_feed", fake_feed)

    result = asyncio.run(langgraph_resident.run_resident_langgraph(context))

    assert result["engine"] == "routine_resident_v1+keyword_search_v1"
    assert result["status"] == "completed"
    assert result["publish_result"]["public_action_count"] == 1
    assert result["inbox_lane"]["outcome"] == "INBOX_ACTION_SUCCEEDED"
    assert result["llm_usage_summary"]["inbox"]["provider_call_count"] == 2
    assert result["llm_usage_summary"]["routine"]["provider_call_count"] == 0
    assert result["llm_usage_summary"]["feed"]["provider_call_count"] == 0
    assert call_order == ["inbox", "routine", "feed"]


def test_combined_inbox_lane_distinguishes_llm_no_action_from_not_run(
    monkeypatch,
) -> None:
    handled: list[tuple[int, str]] = []

    class FakeDb:
        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    context = SimpleNamespace(
        db=FakeDb(),
        character=SimpleNamespace(id="character-inbox-no-action"),
        run_id="run-inbox-no-action",
    )
    monkeypatch.setattr(langgraph_resident, "_current_daypart_context", lambda _ctx: {})
    monkeypatch.setattr(
        langgraph_resident, "_inbox_lane_relationship_memory", lambda _ctx: {}
    )

    class NoActionGraph:
        def __init__(self, tracker) -> None:
            self.tracker = tracker

        async def ainvoke(self, _state, config=None):
            assert config is not None
            self.tracker.calls.append(
                {
                    "lane": "inbox_action_planner",
                    "call_type": "generate_content",
                    "usage": {},
                }
            )
            return {
                "completed_nodes": [
                    *langgraph_resident._INBOX_LANE_PRECOMPLETED_NODES,
                    "InboxObserver",
                    "InboxActionPlanner",
                    "BundleComposer",
                    "ActionBudgetTrimmer",
                    "WriteTaskComposer",
                    "CommunityExecutor",
                ],
                "inbox_observation": {
                    "observed_count": 1,
                    "items": [
                        {
                            "notification_id": 71,
                            "source_post_id": "post-inbox-no-action",
                        }
                    ],
                },
                "inbox_action_plan": {"raw_selected_action_count": 0},
                "action_plan": {"inbox_actions": []},
                "publish_result": {"actions": [], "public_action_count": 0},
            }

    monkeypatch.setattr(
        langgraph_resident,
        "_build_graph",
        lambda _ctx, tracker: NoActionGraph(tracker),
    )
    monkeypatch.setattr(
        langgraph_resident.langgraph_social_apply,
        "mark_notification_handled_without_public_action",
        lambda _db, *, notification_id, handling_outcome, **_kwargs: handled.append(
            (notification_id, handling_outcome)
        ),
    )

    no_action = asyncio.run(langgraph_resident._run_combined_inbox_lane(context))

    assert no_action["outcome"] == "LLM_DECIDED_NO_ACTION"
    assert no_action["planner_invoked"] is True
    assert no_action["decision_source"] == "llm"
    assert no_action["provider_call_count"] == 1
    assert no_action["public_action_count"] == 0
    assert no_action["handled_notification_count"] == 1
    assert handled == [(71, "LLM_DECIDED_NO_ACTION")]

    class NotRunGraph:
        async def ainvoke(self, _state, config=None):
            assert config is not None
            return {
                "completed_nodes": list(
                    langgraph_resident._INBOX_LANE_PRECOMPLETED_NODES
                ),
                "publish_result": {"actions": [], "public_action_count": 0},
            }

    monkeypatch.setattr(
        langgraph_resident,
        "_build_graph",
        lambda _ctx, _tracker: NotRunGraph(),
    )
    not_run = asyncio.run(langgraph_resident._run_combined_inbox_lane(context))

    assert not_run["outcome"] == "INBOX_NOT_RUN"
    assert not_run["planner_invoked"] is False
    assert not_run["decision_source"] == "code"
    assert not_run["handled_notification_count"] == 0


def test_scoped_post_pair_and_identity_are_validated_by_service() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        with pytest.raises(community_service.PostWorldScopeError):
            community_service.create_post(
                db,
                fixture.user,
                schemas.PostCreate(
                    title="Invalid scope",
                    body="Only one half of the scope was supplied.",
                    author_character_id=fixture.character.id,
                ),
                world_id=fixture.world.id,
            )

        assert db.scalar(select(func.count(models.Post.id))) == 0


@pytest.mark.skipif(
    not os.getenv("SECURITY_CONCURRENCY_DATABASE_URL"),
    reason="SECURITY_CONCURRENCY_DATABASE_URL is required",
)
def test_same_tick_is_single_flight_across_twenty_postgres_sessions() -> None:
    database_url = os.environ["SECURITY_CONCURRENCY_DATABASE_URL"]
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=0,
    )
    now = _utc(datetime(2026, 8, 10, 10, 5))
    barrier = Barrier(20)

    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        fixture_ids = {
            "user_id": fixture.user.id,
            "character_id": fixture.character.id,
            "credential_id": fixture.credential.id,
            "episode_id": fixture.morning_episode.id,
            "world_id": fixture.world.id,
            "world_character_id": fixture.world_character.id,
        }
        for index in range(20):
            db.add(
                models.AgentRun(
                    id=f"run-concurrent-{index}",
                    user_id=fixture.user.id,
                    character_id=fixture.character.id,
                    credential_id=fixture.credential.id,
                    agent_id="agent-routine",
                    session_key=f"routine-concurrent:{index}",
                    status="running",
                    created_at=now,
                )
            )
        db.commit()

    def attempt(index: int) -> tuple[str, int]:
        with Session(engine, expire_on_commit=False) as db:
            character = db.get(models.Character, fixture_ids["character_id"])
            credential = db.get(models.LlmCredential, fixture_ids["credential_id"])
            assert character is not None
            assert credential is not None
            context = LangGraphResidentContext(
                db=db,
                run_id=f"run-concurrent-{index}",
                user_id=fixture_ids["user_id"],
                agent_id="agent-routine",
                session_key=f"routine-concurrent:{index}",
                character=character,
                credential=credential,
                state=None,
                activity_policy=ActivityPolicy(
                    within_active_hours=True,
                    allowed_actions=("post",),
                    blocked_reasons={},
                    next_tick_at=now + timedelta(hours=1),
                    summary="allowed=post",
                ),
                selected_post_id=None,
                run_started_at=now,
            )
            provider = FakeRoutineProvider()
            barrier.wait()
            result = asyncio.run(
                routine_post_runtime.run_routine_post_runtime(
                    context,
                    provider=provider,
                )
            )
            return str(result["routine_outcome"]), provider.calls

    try:
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(attempt, range(20)))

        outcomes = [outcome for outcome, _calls in results]
        assert outcomes.count("POST_SUCCEEDED") == 1
        assert set(outcomes).issubset(
            {
                "POST_SUCCEEDED",
                "BEAT_ALREADY_CLAIMED",
                "BEAT_ALREADY_TERMINAL",
                "BEAT_NOT_DUE",
            }
        )
        assert sum(calls for _outcome, calls in results) == 1

        with Session(engine) as db:
            beats = list(
                db.scalars(
                    select(models.ActivityBeat).where(
                        models.ActivityBeat.episode_id == fixture_ids["episode_id"]
                    )
                )
            )
            posts = list(
                db.scalars(
                    select(models.Post).where(
                        models.Post.world_id == fixture_ids["world_id"],
                        models.Post.author_world_character_id
                        == fixture_ids["world_character_id"],
                    )
                )
            )
            assert len(beats) == 1
            assert beats[0].status == "succeeded"
            assert len(posts) == 1
            assert beats[0].source_post_id == posts[0].id
    finally:
        engine.dispose()
