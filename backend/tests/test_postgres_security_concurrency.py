import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import os
from threading import Barrier, Lock
from time import sleep
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, inspect, select, text
from sqlalchemy.orm import Session

from app import models, schemas
from app.cruds import agent_runs as agent_run_crud
from app.cruds import community as community_crud
from app.services import agents as agent_service
from app.services import auth as auth_service
from app.services import community_abuse_quota
from app.services import external_auth_verification
from app.services import local_bot_quota
from app.services import login_throttle
from app.services import lore_parser_quota
from app.services import messages as message_service
from app.services import daily_activity_plans
from app.services import worlds as world_service
from app.services import world_character_contracts
from app.services.direct_llm import DirectLlmResponse


DATABASE_URL = os.getenv("SECURITY_CONCURRENCY_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="SECURITY_CONCURRENCY_DATABASE_URL is required",
)


def _engine():
    assert DATABASE_URL is not None
    return create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=60,
        max_overflow=0,
    )


def test_security_migration_schema_contract() -> None:
    engine = _engine()
    inspector = inspect(engine)
    expected_tables = {
        "auth_external_verification_reservations",
        "auth_google_signup_grants",
        "auth_login_throttle_buckets",
        "community_mutation_quota_buckets",
        "local_bot_action_quota_buckets",
        "local_bot_read_quota_buckets",
        "lore_parser_leases",
        "world_activity_candidates",
        "world_activity_repertoires",
        "world_character_setup_attempts",
        "world_community_profiles",
        "daily_activity_plans",
        "daily_activity_plan_items",
        "activity_episodes",
        "activity_beats",
        "activity_event_consumptions",
        "activity_plan_revisions",
        "joint_activities",
        "joint_activity_participants",
        "joint_activity_representation_claims",
    }
    assert expected_tables.issubset(set(inspector.get_table_names()))
    assert {
        item["name"]
        for item in inspector.get_check_constraints(
            "local_bot_action_quota_buckets"
        )
    } == {
        "ck_local_bot_action_quota_label",
        "ck_local_bot_action_quota_used_nonnegative",
    }
    assert {
        item["name"]
        for item in inspector.get_check_constraints("auth_login_throttle_buckets")
    } == {
        "ck_auth_login_throttle_failure_nonnegative",
        "ck_auth_login_throttle_scope",
    }
    auth_session_columns = {
        item["name"]: item for item in inspector.get_columns("auth_sessions")
    }
    assert auth_session_columns["expires_at"]["nullable"] is True
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "20260809_0074"
        )


def test_daily_activity_plan_is_singleton_across_twenty_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-p3-{suffix}"
    character_id = f"character-p3-{suffix}"
    world_id = f"world-p3-{suffix}"
    membership_id = f"membership-p3-{suffix}"
    world_character_id = f"wc-p3-{suffix}"
    profile_id = f"profile-p3-{suffix}"
    repertoire_id = f"repertoire-p3-{suffix}"
    now = datetime(2026, 8, 9, 1, 0, tzinfo=UTC)
    barrier = Barrier(20)

    with Session(engine) as db:
        user = models.User(
            id=user_id,
            email=f"{suffix}@example.invalid",
            display_name=user_id,
            display_name_normalized=user_id,
            profile_setup_completed=True,
        )
        character = models.Character(
            id=character_id,
            owner_id=user_id,
            name="P3 concurrency character",
            handle=f"p3_{suffix[:20]}",
            persona_summary="A deterministic P3 concurrency fixture.",
        )
        world = models.World(
            id=world_id,
            slug=f"p3-{suffix}",
            owner_user_id=user_id,
            name="P3 concurrency World",
            tagline="A World for deterministic daily plan concurrency testing.",
            setting_description="A bounded fixture World with deterministic routines.",
            daily_life_description="Characters follow four local-time dayparts.",
            genre_tags=["test"],
            tone_tags=["safe"],
            timezone="Asia/Seoul",
            language="ko",
            visibility="private",
            join_policy="open",
            status="published",
            contract_version="world-v1",
            contract_hash="a" * 64,
            readiness_status="publish_ready",
            create_idempotency_key=f"create-{suffix}",
        )
        db.add_all([user, world])
        db.flush()
        db.add(character)
        db.flush()
        membership = models.WorldMembership(
            id=membership_id,
            world_id=world_id,
            user_id=user_id,
            role="member",
            status="active",
            joined_at=now,
        )
        db.add(membership)
        db.flush()
        character_hash = world_character_contracts.character_contract_hash(character)
        world_character = models.WorldCharacter(
            id=world_character_id,
            world_id=world_id,
            character_id=character_id,
            membership_id=membership_id,
            role_key="member",
            status="active",
            autonomous_enabled=False,
            local_profile={"background": "concurrency fixture"},
            character_contract_hash=character_hash,
            world_contract_hash=world.contract_hash,
        )
        db.add(world_character)
        db.flush()
        profile = models.WorldCommunityProfile(
            id=profile_id,
            world_character_id=world_character_id,
            status="ready",
            visible_summary="P3 concurrency fixture",
            core_interests=["testing"],
            adjacent_interests=["routines"],
            avoid_topics=[],
            discovery_openness=50,
            search_keywords=["testing"],
            action_profile={},
            schema_version=1,
            generator_version="test-v1",
            character_contract_hash=character_hash,
            world_contract_hash=world.contract_hash,
            provider="google",
            model="gemini-test",
            credential_id=f"credential-{suffix}",
            generated_at=now,
            approved_at=now,
        )
        db.add(profile)
        db.flush()
        repertoire = models.WorldActivityRepertoire(
            id=repertoire_id,
            world_character_id=world_character_id,
            status="ready",
            schema_version=1,
            generator_version="test-v1",
            character_contract_hash=character_hash,
            world_contract_hash=world.contract_hash,
            community_profile_id=profile_id,
            provider="google",
            model="gemini-test",
            credential_id=f"credential-{suffix}",
            validation_summary={"candidate_count": 40},
            generated_at=now,
            approved_at=now,
        )
        db.add(repertoire)
        db.flush()
        for daypart in ("dawn", "morning", "afternoon", "evening"):
            for ordinal in range(1, 11):
                signature = sha256(
                    f"{world_character_id}|{daypart}|{ordinal}".encode()
                ).hexdigest()
                db.add(
                    models.WorldActivityCandidate(
                        id=f"candidate-{suffix[:8]}-{daypart}-{ordinal}",
                        repertoire_id=repertoire_id,
                        daypart=daypart,
                        ordinal=ordinal,
                        activity_kind="duty" if ordinal % 2 else "rest",
                        title=f"{daypart} activity {ordinal}",
                        activity_seed=f"Complete {daypart} activity {ordinal}.",
                        social_mode="solo",
                        canonical_signature=signature,
                        enabled=True,
                    )
                )
        db.commit()

    def prepare(index: int) -> str:
        with Session(engine, expire_on_commit=False) as db:
            user = db.get(models.User, user_id)
            assert user is not None
            barrier.wait()
            result = daily_activity_plans.prepare_activity_plan(
                db,
                character_id=character_id,
                world_id=world_id,
                user=user,
                data=schemas.DailyActivityPlanPrepareCreate(
                    idempotency_key=f"p3-concurrent-{index}"
                ),
                now=now,
            )
            return result.id

    try:
        with ThreadPoolExecutor(max_workers=20) as executor:
            plan_ids = list(executor.map(prepare, range(20)))
        assert len(set(plan_ids)) == 1
        with Session(engine) as db:
            assert db.scalar(
                select(func.count(models.DailyActivityPlan.id)).where(
                    models.DailyActivityPlan.world_character_id == world_character_id
                )
            ) == 1
            assert db.scalar(
                select(func.count(models.DailyActivityPlanItem.id)).where(
                    models.DailyActivityPlanItem.world_character_id
                    == world_character_id
                )
            ) == 4
    finally:
        with Session(engine) as db:
            item_ids = select(models.DailyActivityPlanItem.id).where(
                models.DailyActivityPlanItem.world_character_id == world_character_id
            )
            episode_ids = select(models.ActivityEpisode.id).where(
                models.ActivityEpisode.world_character_id == world_character_id
            )
            db.execute(
                delete(models.ActivityBeat).where(
                    models.ActivityBeat.episode_id.in_(episode_ids)
                )
            )
            db.execute(
                delete(models.ActivityEpisode).where(
                    models.ActivityEpisode.world_character_id == world_character_id
                )
            )
            db.execute(
                delete(models.DailyActivityPlanItem).where(
                    models.DailyActivityPlanItem.id.in_(item_ids)
                )
            )
            db.execute(
                delete(models.DailyActivityPlan).where(
                    models.DailyActivityPlan.world_character_id == world_character_id
                )
            )
            db.execute(
                delete(models.WorldActivityCandidate).where(
                    models.WorldActivityCandidate.repertoire_id == repertoire_id
                )
            )
            db.execute(
                delete(models.WorldActivityRepertoire).where(
                    models.WorldActivityRepertoire.id == repertoire_id
                )
            )
            db.execute(
                delete(models.WorldCommunityProfile).where(
                    models.WorldCommunityProfile.id == profile_id
                )
            )
            db.execute(
                delete(models.WorldCharacter).where(
                    models.WorldCharacter.id == world_character_id
                )
            )
            db.execute(
                delete(models.WorldMembership).where(
                    models.WorldMembership.id == membership_id
                )
            )
            db.execute(delete(models.World).where(models.World.id == world_id))
            db.execute(
                delete(models.Character).where(models.Character.id == character_id)
            )
            db.execute(delete(models.User).where(models.User.id == user_id))
            db.commit()
        engine.dispose()


def test_world_row_version_serializes_concurrent_writers() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-world-concurrency-{suffix}"
    barrier = Barrier(2)

    with Session(engine) as db:
        owner = models.User(
            id=user_id,
            email=f"{suffix}@example.invalid",
            display_name=user_id,
            display_name_normalized=user_id,
            profile_setup_completed=True,
        )
        db.add(owner)
        db.commit()
        created = world_service.create_world(
            db,
            user=owner,
            data=schemas.WorldDraftCreate(
                name="동시성 검증 World",
                tagline="두 작성자의 오래된 수정을 동시에 막는 검증 세계",
                setting_description="세계" * 100,
                daily_life_description="일상" * 75,
                genre_tags=["test"],
                tone_tags=["safe"],
                idempotency_key=f"create-{suffix}",
            ),
        )
        world_id = created.world.id
        row_version = created.world.row_version

    def attempt(label: str) -> str:
        with Session(engine) as db:
            owner = db.get(models.User, user_id)
            assert owner is not None
            barrier.wait()
            try:
                world_service.update_world(
                    db,
                    world_id=world_id,
                    user=owner,
                    data=schemas.WorldUpdate(
                        row_version=row_version,
                        tagline=f"{label} 작성자가 저장한 충분히 긴 World 소개 문장",
                    ),
                )
            except world_service.WorldRowVersionConflictError:
                db.rollback()
                return "conflict"
            return "updated"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, ("첫 번째", "두 번째")))
        assert sorted(results) == ["conflict", "updated"]
        with Session(engine) as db:
            world = db.get(models.World, world_id)
            assert world is not None
            assert world.row_version == row_version + 1
    finally:
        with Session(engine) as db:
            db.execute(
                delete(models.WorldMembership).where(
                    models.WorldMembership.world_id == world_id
                )
            )
            db.execute(delete(models.World).where(models.World.id == world_id))
            db.execute(delete(models.User).where(models.User.id == user_id))
            db.commit()


def test_resident_character_assignment_is_unique_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-resident-{suffix}"
    character_id = f"char-resident-{suffix}"
    credential_id = f"cred-resident-{suffix}"
    agent_ids = [f"resident-slot-{suffix}-1", f"resident-slot-{suffix}-2"]
    barrier = Barrier(12)
    next_tick_at = datetime.now(UTC) + timedelta(minutes=5)

    with Session(engine) as db:
        db.add(
            models.User(
                id=user_id,
                email=f"{suffix}@example.invalid",
                display_name=user_id,
                display_name_normalized=user_id,
                profile_setup_completed=True,
            )
        )
        db.add(
            models.Character(
                id=character_id,
                owner_id=user_id,
                name=character_id,
                handle=f"resident_{suffix[:20]}",
                persona_summary="resident assignment fixture",
                execution_mode="llm",
            )
        )
        db.add(
            models.LlmCredential(
                id=credential_id,
                owner_id=user_id,
                character_id=character_id,
                provider="google",
                purpose="agent",
                model="gemini-3.1-flash-lite",
                auth_profile_id=f"google:{character_id}",
                label=character_id,
                encrypted_api_key="synthetic-encrypted",
                key_fingerprint=suffix[:16],
                enabled=True,
            )
        )
        db.commit()

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            slot = agent_run_crud.assign_resident_slot(
                db,
                agent_ids=agent_ids,
                user_id=user_id,
                character_id=character_id,
                credential_id=credential_id,
                heartbeat_interval_seconds=300,
                next_tick_at=next_tick_at,
            )
            assert slot is not None
            return slot.agent_id

    try:
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(lambda _index: attempt(), range(12)))
        assert len(set(results)) == 1
        assert set(results).issubset(set(agent_ids))
        with Session(engine) as db:
            assigned = list(
                db.scalars(
                    select(models.AgentSlot).where(
                        models.AgentSlot.assigned_character_id == character_id
                    )
                )
            )
            assert len(assigned) == 1
            assert assigned[0].agent_id in agent_ids
            assert assigned[0].assigned_user_id == user_id
            assert assigned[0].assigned_credential_id == credential_id
    finally:
        with Session(engine) as db:
            db.execute(
                delete(models.AgentSlot).where(models.AgentSlot.agent_id.in_(agent_ids))
            )
            db.execute(
                delete(models.LlmCredential).where(
                    models.LlmCredential.id == credential_id
                )
            )
            db.execute(
                delete(models.Character).where(models.Character.id == character_id)
            )
            db.execute(delete(models.User).where(models.User.id == user_id))
            db.commit()


def test_message_response_lease_is_single_flight_across_postgres_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-message-lease-{suffix}"
    character_ids = [
        f"char-message-lease-{suffix}-{index}" for index in range(2)
    ]
    credential_id = f"cred-message-lease-{suffix}"
    thread_ids = [f"thread-message-lease-{suffix}-{index}" for index in range(2)]
    barrier = Barrier(2)
    provider_lock = Lock()
    provider_calls = 0

    async def fake_generate_text(**_kwargs):
        nonlocal provider_calls
        with provider_lock:
            provider_calls += 1
        await asyncio.sleep(0.2)
        return DirectLlmResponse(
            text="synthetic response",
            parsed=None,
            usage={},
        )

    monkeypatch.setattr(message_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(message_service.security, "decrypt_secret", lambda _value: "fake")

    with Session(engine) as db:
        db.add(
            models.User(
                id=user_id,
                email=f"{suffix}@example.invalid",
                display_name=user_id,
                display_name_normalized=user_id,
                profile_setup_completed=True,
            )
        )
        db.add_all(
            [
                models.Character(
                    id=character_id,
                    owner_id=user_id,
                    name=character_id,
                    handle=f"message_lease_{suffix[:18]}_{index}",
                    persona_summary="message lease fixture",
                    execution_mode="llm",
                )
                for index, character_id in enumerate(character_ids)
            ]
        )
        db.add(
            models.LlmCredential(
                id=credential_id,
                owner_id=user_id,
                character_id=None,
                provider="google",
                purpose="message",
                model=message_service.DEFAULT_MESSAGE_MODEL,
                auth_profile_id=f"google:message:{user_id}",
                label=credential_id,
                encrypted_api_key="synthetic-encrypted",
                key_fingerprint=suffix[:16],
                enabled=True,
            )
        )
        db.add(
            models.UserMessagePreference(
                user_id=user_id,
                credential_source="message_key",
                default_model=message_service.DEFAULT_MESSAGE_MODEL,
            )
        )
        db.add_all(
            [
                models.MessageThread(
                    id=thread_id,
                    requester_id=user_id,
                    character_id=character_id,
                    selected_model=message_service.DEFAULT_MESSAGE_MODEL,
                )
                for thread_id, character_id in zip(thread_ids, character_ids, strict=True)
            ]
        )
        db.commit()

    def attempt(thread_id: str, start_barrier: Barrier) -> str:
        with Session(engine) as db:
            user = db.get(models.User, user_id)
            assert user is not None
            start_barrier.wait()
            try:
                asyncio.run(
                    message_service.send_message(
                        db,
                        user,
                        thread_id,
                        schemas.MessageMessageCreate(content="synthetic"),
                    )
                )
            except message_service.MessageInFlightError:
                return "in-flight"
            return "sent"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            same_thread = sorted(
                executor.map(
                    lambda _index: attempt(thread_ids[0], barrier),
                    range(2),
                )
            )
        assert same_thread == ["in-flight", "sent"]
        assert provider_calls == 1

        different_barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            different_threads = list(
                executor.map(
                    lambda thread_id: attempt(thread_id, different_barrier),
                    thread_ids,
                )
            )
        assert different_threads == ["sent", "sent"]
        assert provider_calls == 3

        with Session(engine) as db:
            rows = list(
                db.scalars(
                    select(models.MessageMessage).where(
                        models.MessageMessage.thread_id.in_(thread_ids)
                    )
                )
            )
            assert sum(row.role == "user" for row in rows) == 3
            assert sum(row.role == "assistant" for row in rows) == 3
            threads = list(
                db.scalars(
                    select(models.MessageThread).where(
                        models.MessageThread.id.in_(thread_ids)
                    )
                )
            )
            assert all(thread.response_lease_token is None for thread in threads)
            assert all(thread.response_lease_expires_at is None for thread in threads)

            retry_user_message = models.MessageMessage(
                thread_id=thread_ids[1],
                role="user",
                content="retry fixture",
                model=message_service.DEFAULT_MESSAGE_MODEL,
                status="ok",
            )
            retry_assistant_message = models.MessageMessage(
                thread_id=thread_ids[1],
                role="assistant",
                content=message_service.MODEL_BUSY_MESSAGE,
                model=message_service.DEFAULT_MESSAGE_MODEL,
                status="error",
                error_code="model_busy",
            )
            db.add_all([retry_user_message, retry_assistant_message])
            db.commit()
            db.refresh(retry_assistant_message)
            retry_message_id = retry_assistant_message.id

        cross_barrier = Barrier(2)

        def cross_attempt(kind: str) -> str:
            with Session(engine) as db:
                user = db.get(models.User, user_id)
                assert user is not None
                cross_barrier.wait()
                try:
                    if kind == "send":
                        asyncio.run(
                            message_service.send_message(
                                db,
                                user,
                                thread_ids[1],
                                schemas.MessageMessageCreate(content="cross send"),
                            )
                        )
                    else:
                        asyncio.run(
                            message_service.retry_message(
                                db,
                                user,
                                thread_ids[1],
                                retry_message_id,
                            )
                        )
                except message_service.MessageInFlightError:
                    return "in-flight"
                return kind

        with ThreadPoolExecutor(max_workers=2) as executor:
            cross_results = list(executor.map(cross_attempt, ("send", "retry")))
        assert cross_results.count("in-flight") == 1
        assert provider_calls == 4

        with Session(engine) as db:
            thread = db.get(models.MessageThread, thread_ids[0])
            user = db.get(models.User, user_id)
            assert thread is not None and user is not None
            thread.response_lease_token = "expired-token"
            thread.response_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
            replacement = message_service._acquire_response_lease(
                db,
                user,
                thread.id,
            )
            assert replacement != "expired-token"
            message_service._release_response_lease(db, thread.id, replacement)

        async def fake_provider_error(**_kwargs):
            raise message_service.DirectLlmError("synthetic provider failure")

        monkeypatch.setattr(
            message_service,
            "generate_text",
            fake_provider_error,
        )
        with Session(engine) as db:
            user = db.get(models.User, user_id)
            assert user is not None
            with pytest.raises(message_service.MessageModelBusyError):
                asyncio.run(
                    message_service.send_message(
                        db,
                        user,
                        thread_ids[0],
                        schemas.MessageMessageCreate(content="provider failure"),
                    )
                )
            thread = db.get(models.MessageThread, thread_ids[0])
            assert thread is not None
            assert thread.response_lease_token is None
            assert thread.response_lease_expires_at is None
    finally:
        with Session(engine) as db:
            db.execute(
                delete(models.MessageMessage).where(
                    models.MessageMessage.thread_id.in_(thread_ids)
                )
            )
            db.execute(
                delete(models.MessageThread).where(
                    models.MessageThread.id.in_(thread_ids)
                )
            )
            db.execute(
                delete(models.UserMessagePreference).where(
                    models.UserMessagePreference.user_id == user_id
                )
            )
            db.execute(
                delete(models.LlmCredential).where(
                    models.LlmCredential.id == credential_id
                )
            )
            db.execute(
                delete(models.Character).where(models.Character.id.in_(character_ids))
            )
            db.execute(delete(models.User).where(models.User.id == user_id))
            db.commit()


def test_local_bot_quotas_are_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-security-{suffix}"
    character_id = f"char-security-{suffix}"
    local_key_id = f"key-security-{suffix}"
    now = datetime.now(UTC)
    barrier = Barrier(2)

    with Session(engine) as db:
        db.add(
            models.User(
                id=user_id,
                email=f"{suffix}@example.invalid",
                display_name=user_id,
                display_name_normalized=user_id,
                profile_setup_completed=True,
                feed_content_filter="all",
            )
        )
        db.add(
            models.Character(
                id=character_id,
                owner_id=user_id,
                name=character_id,
                handle=f"security_{suffix[:20]}",
                one_liner="",
                personality="",
                speech_style="",
                worldview="",
                topic_preferences="",
                safety_rules="",
                persona_summary="security concurrency fixture",
            )
        )
        db.add(
            models.AgentLocalKey(
                id=local_key_id,
                owner_id=user_id,
                character_id=character_id,
                token_hash=(suffix * 2)[:64],
                token_prefix="angmoo_local_security",
                enabled=True,
            )
        )
        db.commit()

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            quota = local_bot_quota.lock_action_quota(
                db,
                character_id=character_id,
                labels=("reply",),
                now=now,
            )
            try:
                quota.ensure_allowed(
                    "reply",
                    cooldown=timedelta(0),
                    max_per_day=1,
                    message="reply limited",
                )
            except local_bot_quota.QuotaExceeded:
                db.rollback()
                return "limited"
            quota.consume(("reply",))
            sleep(0.1)
            db.commit()
            return "allowed"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = sorted(executor.map(lambda _index: attempt(), range(2)))
        assert results == ["allowed", "limited"]
        with Session(engine) as db:
            row = db.scalar(
                select(models.LocalBotActionQuotaBucket).where(
                    models.LocalBotActionQuotaBucket.character_id == character_id,
                    models.LocalBotActionQuotaBucket.action_label == "reply",
                )
            )
            assert row is not None
            assert row.used_count == 1

        read_barrier = Barrier(2)

        def read_attempt() -> str:
            with Session(engine) as db:
                read_barrier.wait()
                try:
                    local_bot_quota.consume_read(
                        db,
                        local_key_id=local_key_id,
                        now=now,
                        limit=1,
                        window=timedelta(minutes=1),
                    )
                except local_bot_quota.QuotaExceeded:
                    db.rollback()
                    return "limited"
                return "allowed"

        with ThreadPoolExecutor(max_workers=2) as executor:
            read_results = sorted(executor.map(lambda _index: read_attempt(), range(2)))
        assert read_results == ["allowed", "limited"]
        with Session(engine) as db:
            read_row = db.get(models.LocalBotReadQuotaBucket, local_key_id)
            assert read_row is not None
            assert read_row.used_count == 1
    finally:
        with Session(engine) as db:
            db.execute(
                delete(models.LocalBotReadQuotaBucket).where(
                    models.LocalBotReadQuotaBucket.local_key_id == local_key_id
                )
            )
            db.execute(
                delete(models.LocalBotActionQuotaBucket).where(
                    models.LocalBotActionQuotaBucket.character_id == character_id
                )
            )
            db.execute(
                delete(models.AgentLocalKey).where(
                    models.AgentLocalKey.id == local_key_id
                )
            )
            db.execute(
                delete(models.Character).where(models.Character.id == character_id)
            )
            db.execute(delete(models.User).where(models.User.id == user_id))
            db.commit()


def test_login_throttle_is_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    email = f"{suffix}@example.invalid"
    source = f"security-source-{suffix}"
    now = datetime.now(UTC)

    with Session(engine) as db:
        throttle = login_throttle.lock_login_throttle(
            db,
            normalized_email=email,
            source=source,
            now=now,
        )
        for row in throttle.rows.values():
            row.failure_count = 4
            row.window_started_at = now
            row.blocked_until = None
        subject_hashes = [row.subject_hash for row in throttle.rows.values()]
        db.commit()

    barrier = Barrier(2)

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            throttle = login_throttle.lock_login_throttle(
                db,
                normalized_email=email,
                source=source,
                now=now,
            )
            if throttle.retry_after_seconds() is not None:
                db.rollback()
                return "limited"
            throttle.record_failure()
            sleep(0.1)
            db.commit()
            return "recorded"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = sorted(executor.map(lambda _index: attempt(), range(2)))
        assert results == ["limited", "recorded"]
        with Session(engine) as db:
            rows = list(
                db.scalars(
                    select(models.AuthLoginThrottleBucket).where(
                        models.AuthLoginThrottleBucket.subject_hash.in_(subject_hashes)
                    )
                )
            )
            assert len(rows) == 2
            assert {row.failure_count for row in rows} == {5}
            assert all(row.blocked_until is not None for row in rows)
    finally:
        with Session(engine) as db:
            db.execute(
                delete(models.AuthLoginThrottleBucket).where(
                    models.AuthLoginThrottleBucket.subject_hash.in_(subject_hashes)
                )
            )
            db.commit()


def test_google_verification_reservation_is_atomic_across_postgres_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    source = f"google-security-{uuid4().hex}"
    now = datetime.now(UTC)
    monkeypatch.setattr(
        external_auth_verification.settings,
        "GOOGLE_AUTH_VERIFY_SOURCE_PER_MINUTE",
        1,
    )
    monkeypatch.setattr(
        external_auth_verification.settings,
        "GOOGLE_AUTH_VERIFY_SOURCE_PER_15_MINUTES",
        10,
    )
    monkeypatch.setattr(
        external_auth_verification.settings,
        "GOOGLE_AUTH_VERIFY_GLOBAL_PER_MINUTE",
        10,
    )
    monkeypatch.setattr(
        external_auth_verification.settings,
        "GOOGLE_AUTH_VERIFY_MAX_IN_FLIGHT",
        10,
    )
    attempt_count = 12
    barrier = Barrier(attempt_count)

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            try:
                reservation = (
                    external_auth_verification.reserve_google_verification(
                        db,
                        source=source,
                        now=now,
                    )
                )
            except external_auth_verification.ExternalVerificationRateLimitedError:
                return "limited"
            external_auth_verification.complete_google_verification(
                db,
                reservation.id,
                outcome_class="invalid",
                now=now,
            )
            return "allowed"

    with ThreadPoolExecutor(max_workers=attempt_count) as executor:
        results = list(executor.map(lambda _index: attempt(), range(attempt_count)))
    assert results.count("allowed") == 1
    assert results.count("limited") == attempt_count - 1


def test_google_signup_grant_is_consumed_once_across_postgres_sessions() -> None:
    engine = _engine()
    jti = uuid4().hex
    now = datetime.now(UTC)
    with Session(engine) as db:
        db.add(
            models.AuthGoogleSignupGrant(
                jti_hash=auth_service._pending_signup_jti_hash(jti),
                created_at=now,
                expires_at=now + timedelta(minutes=10),
            )
        )
        db.commit()
    attempt_count = 12
    barrier = Barrier(attempt_count)

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            try:
                grant = auth_service._lock_pending_google_signup_grant(
                    db,
                    jti=jti,
                )
            except auth_service.InvalidGoogleSignupTokenError:
                return "rejected"
            grant.consumed_at = datetime.now(UTC)
            sleep(0.1)
            db.commit()
            return "consumed"

    with ThreadPoolExecutor(max_workers=attempt_count) as executor:
        results = list(executor.map(lambda _index: attempt(), range(attempt_count)))
    assert results.count("consumed") == 1
    assert results.count("rejected") == attempt_count - 1


def test_direct_user_like_is_unique_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-like-{suffix}"
    post_id = f"post-like-{suffix}"
    with Session(engine) as db:
        user = models.User(
            id=user_id,
            email=f"{suffix}@example.invalid",
            display_name=user_id,
            display_name_normalized=user_id,
            profile_setup_completed=True,
        )
        db.add(user)
        db.add(
            models.Post(
                id=post_id,
                author_user_id=user_id,
                author_name=user_id,
                title="synthetic",
                body="synthetic",
                post_type="text",
            )
        )
        db.commit()
    attempt_count = 50
    barrier = Barrier(attempt_count)

    def attempt() -> bool:
        with Session(engine) as db:
            user = db.get(models.User, user_id)
            post = db.get(models.Post, post_id)
            assert user is not None and post is not None
            barrier.wait()
            _like, created = community_crud.like_post(
                db,
                post=post,
                user=user,
                character=None,
            )
            return created

    with ThreadPoolExecutor(max_workers=attempt_count) as executor:
        results = list(executor.map(lambda _index: attempt(), range(attempt_count)))
    assert results.count(True) == 1
    assert results.count(False) == attempt_count - 1
    with Session(engine) as db:
        rows = list(
            db.scalars(
                select(models.PostLike).where(
                    models.PostLike.post_id == post_id,
                    models.PostLike.user_id == user_id,
                    models.PostLike.character_id.is_(None),
                )
            )
        )
        assert len(rows) == 1


def test_community_reply_quota_is_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    user_id = f"community-quota-{uuid4().hex}"
    now = datetime.now(UTC)
    with Session(engine) as db:
        for _ in range(9):
            community_abuse_quota.consume(
                db,
                user_id=user_id,
                action="reply",
                now=now,
            )
            db.commit()
    barrier = Barrier(2)

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            try:
                community_abuse_quota.consume(
                    db,
                    user_id=user_id,
                    action="reply",
                    now=now,
                )
            except community_abuse_quota.CommunityQuotaExceeded:
                return "limited"
            sleep(0.1)
            db.commit()
            return "allowed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(executor.map(lambda _index: attempt(), range(2)))
    assert results == ["allowed", "limited"]


def test_lore_parser_global_capacity_is_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    attempt_count = 4
    barrier = Barrier(attempt_count)

    def attempt(index: int) -> str:
        with Session(engine) as db:
            barrier.wait()
            try:
                with lore_parser_quota.parser_lease(
                    db,
                    user_id=f"lore-user-{index}-{uuid4().hex}",
                ):
                    sleep(0.2)
                    return "allowed"
            except lore_parser_quota.LoreParserCapacityError:
                return "limited"

    with ThreadPoolExecutor(max_workers=attempt_count) as executor:
        results = list(executor.map(attempt, range(attempt_count)))
    assert results.count("allowed") == lore_parser_quota.GLOBAL_ACTIVE_LIMIT
    assert (
        results.count("limited")
        == attempt_count - lore_parser_quota.GLOBAL_ACTIVE_LIMIT
    )


def test_agent_creation_quota_is_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-agent-quota-{suffix}"
    with Session(engine) as db:
        db.add(
            models.User(
                id=user_id,
                email=f"{suffix}@example.invalid",
                display_name=user_id,
                display_name_normalized=user_id,
                profile_setup_completed=True,
            )
        )
        db.commit()
    barrier = Barrier(12)

    def attempt(index: int) -> str:
        with Session(engine) as db:
            user = db.get(models.User, user_id)
            assert user is not None
            barrier.wait()
            try:
                agent_service.create_agent(
                    db,
                    user,
                    schemas.AgentCreate(
                        execution_mode="local",
                        name=f"local-{index}",
                        handle=f"local_{suffix[:12]}_{index}",
                    ),
                )
            except agent_service.AgentLimitError:
                db.rollback()
                return "limited"
            return "created"

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(attempt, range(12)))
    assert results.count("created") == agent_service.MAX_LOCAL_AGENTS_PER_USER
    assert results.count("limited") == 12 - agent_service.MAX_LOCAL_AGENTS_PER_USER


def test_first_greeting_claim_is_single_flight_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-greeting-{suffix}"
    character_id = f"char-greeting-{suffix}"
    credential_id = f"cred-greeting-{suffix}"
    now = datetime.now(UTC)
    barrier = Barrier(8)
    counter_lock = Lock()
    provider_calls = 0

    with Session(engine) as db:
        db.add(
            models.User(
                id=user_id,
                email=f"{suffix}@example.invalid",
                display_name=user_id,
                display_name_normalized=user_id,
                profile_setup_completed=True,
            )
        )
        db.add(
            models.Character(
                id=character_id,
                owner_id=user_id,
                name=character_id,
                handle=f"greeting_{suffix[:20]}",
                persona_summary="security greeting fixture",
                execution_mode="llm",
            )
        )
        db.add(
            models.LlmCredential(
                id=credential_id,
                owner_id=user_id,
                character_id=character_id,
                provider="google",
                purpose="agent",
                model="gemini-3.1-flash-lite",
                auth_profile_id=f"google:{character_id}",
                label=character_id,
                encrypted_api_key="synthetic-encrypted",
                key_fingerprint=suffix[:16],
                enabled=True,
            )
        )
        db.commit()

    def attempt(index: int) -> str:
        nonlocal provider_calls
        with Session(engine) as db:
            user = db.get(models.User, user_id)
            character = db.get(models.Character, character_id)
            credential = db.get(models.LlmCredential, credential_id)
            assert user is not None and character is not None and credential is not None
            run_id = f"run-greeting-{suffix}-{index}"
            barrier.wait()
            try:
                agent_service._claim_first_greeting_run(
                    db,
                    user=user,
                    character=character,
                    credential=credential,
                    run_id=run_id,
                    session_key=(
                        "agent:onboarding-first-greeting:first-greeting:"
                        f"{user_id}:{character_id}:{run_id}"
                    ),
                    now=now,
                )
            except (
                agent_service.FirstGreetingCooldownError,
                agent_service.FirstGreetingUnavailableError,
            ):
                return "limited"
            with counter_lock:
                provider_calls += 1
            db.add(
                models.Post(
                    id=f"post-greeting-{suffix}",
                    author_character_id=character_id,
                    author_name=character_id,
                    title="synthetic",
                    body="synthetic",
                    post_type="text",
                )
            )
            db.commit()
            return "created"

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(attempt, range(8)))
        assert results.count("created") == 1
        assert results.count("limited") == 7
        assert provider_calls == 1
        with Session(engine) as db:
            assert len(
                list(
                    db.scalars(
                        select(models.AgentRun).where(
                            models.AgentRun.user_id == user_id,
                            models.AgentRun.session_key.contains(":first-greeting:"),
                        )
                    )
                )
            ) == 1
            assert len(
                list(
                    db.scalars(
                        select(models.Post).where(
                            models.Post.author_character_id == character_id
                        )
                    )
                )
            ) == 1
    finally:
        with Session(engine) as db:
            db.execute(delete(models.AgentRun).where(models.AgentRun.user_id == user_id))
            db.execute(
                delete(models.Post).where(models.Post.author_character_id == character_id)
            )
            db.execute(
                delete(models.LlmCredential).where(models.LlmCredential.id == credential_id)
            )
            db.execute(delete(models.Character).where(models.Character.id == character_id))
            db.execute(delete(models.User).where(models.User.id == user_id))
            db.commit()


def test_message_thread_quota_is_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    requester_id = f"user-message-requester-{suffix}"
    owner_id = f"user-message-owner-{suffix}"
    character_ids = [f"char-message-{suffix}-{index}" for index in range(6)]
    barrier = Barrier(len(character_ids))

    with Session(engine) as db:
        db.add_all(
            [
                models.User(
                    id=requester_id,
                    email=f"requester-{suffix}@example.invalid",
                    display_name=requester_id,
                    display_name_normalized=requester_id,
                    profile_setup_completed=True,
                ),
                models.User(
                    id=owner_id,
                    email=f"owner-{suffix}@example.invalid",
                    display_name=owner_id,
                    display_name_normalized=owner_id,
                    profile_setup_completed=True,
                ),
            ]
        )
        for character_id in character_ids:
            db.add(
                models.Character(
                    id=character_id,
                    owner_id=owner_id,
                    name=character_id,
                    handle=character_id[-40:],
                    persona_summary="security message fixture",
                    execution_mode="llm",
                )
            )
            db.add(
                models.CharacterMessageSetting(
                    character_id=character_id,
                    enabled=True,
                )
            )
        db.add(
            models.UserMessagePreference(
                user_id=requester_id,
                credential_source="message_key",
                default_model=message_service.DEFAULT_MESSAGE_MODEL,
            )
        )
        db.commit()

    def attempt(character_id: str) -> str:
        with Session(engine) as db:
            requester = db.get(models.User, requester_id)
            assert requester is not None
            barrier.wait()
            try:
                message_service.create_or_get_thread(
                    db,
                    requester,
                    schemas.MessageThreadCreate(character_id=character_id),
                )
            except message_service.MessageThreadLimitError:
                return "limited"
            return "created"

    try:
        with ThreadPoolExecutor(max_workers=len(character_ids)) as executor:
            results = list(executor.map(attempt, character_ids))
        assert results.count("created") == message_service.MAX_ACTIVE_THREADS
        assert results.count("limited") == 1
        with Session(engine) as db:
            active_threads = list(
                db.scalars(
                    select(models.MessageThread).where(
                        models.MessageThread.requester_id == requester_id,
                        models.MessageThread.deleted_at.is_(None),
                    )
                )
            )
            assert len(active_threads) == message_service.MAX_ACTIVE_THREADS
    finally:
        with Session(engine) as db:
            db.execute(
                delete(models.MessageThread).where(
                    models.MessageThread.requester_id == requester_id
                )
            )
            db.execute(
                delete(models.UserMessagePreference).where(
                    models.UserMessagePreference.user_id == requester_id
                )
            )
            db.execute(
                delete(models.CharacterMessageSetting).where(
                    models.CharacterMessageSetting.character_id.in_(character_ids)
                )
            )
            db.execute(delete(models.Character).where(models.Character.id.in_(character_ids)))
            db.execute(delete(models.User).where(models.User.id.in_([requester_id, owner_id])))
            db.commit()
