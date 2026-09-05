from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.runtime.routines.lifecycle_references import SqlAlchemyLifecycleReferences
from app import models, schemas
from app.runtime.routines.plan_references import SqlAlchemyPlanReferences
from app.domains.identity import dependencies as api_deps
from app.api.v1.routes import world_activity_runtime as runtime_routes
from app.core.db import Base
from app.domains.routines import public as routines
from app.domains.routines.service import execution as activity_runtime
from app.runtime.routines.activity_references import SqlAlchemyActivityReferences
from app.services import activity_state_contracts
from app.services import daily_activity_plans
from app.services import joint_activity_scheduling
from app.services import routine_post_runtime
from app.services import world_character_setup
from app.services import world_character_contracts


DAYPARTS = ("dawn", "morning", "afternoon", "evening")


@dataclass(frozen=True)
class ReadyCharacter:
    user: models.User
    character: models.Character
    membership: models.WorldMembership
    world_character: models.WorldCharacter
    profile: models.WorldCommunityProfile
    repertoire: models.WorldActivityRepertoire


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


def _user(suffix: str) -> models.User:
    return models.User(
        id=f"user-{suffix}",
        email=f"{suffix}@example.test",
        display_name=f"user-{suffix}",
        display_name_normalized=f"user-{suffix}",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )


def _character(user: models.User, suffix: str) -> models.Character:
    return models.Character(
        id=f"character-{suffix}",
        owner_id=user.id,
        name=f"Mira {suffix}",
        handle=f"mira-{suffix}",
        one_liner="An observant magic academy student",
        personality="Careful, curious, and warm.",
        speech_style="Calm and considerate.",
        worldview="Learning deepens through cooperation.",
        topic_preferences="Alchemy, runes, and friends",
        safety_rules="Never use dangerous spells alone.",
        persona_summary="A second-year alchemy student at Arcana Academy.",
        moderation_status="active",
    )


def _world(owner: models.User) -> models.World:
    return models.World(
        id="world-a",
        slug="arcana-academy",
        owner_user_id=owner.id,
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
        create_idempotency_key="create-world-a",
    )


def _add_ready_character(
    db: Session,
    *,
    world: models.World,
    suffix: str,
) -> ReadyCharacter:
    now = datetime(2026, 8, 9, tzinfo=UTC)
    user = _user(suffix)
    character = _character(user, suffix)
    membership = models.WorldMembership(
        id=f"membership-{suffix}",
        world_id=world.id,
        user_id=user.id,
        role="member",
        status="active",
        joined_at=now,
    )
    world_character = models.WorldCharacter(
        id=f"world-character-{suffix}",
        world_id=world.id,
        character_id=character.id,
        membership_id=membership.id,
        role_key="student",
        status="active",
        autonomous_enabled=False,
        local_profile={"background": "second-year alchemy student"},
    )
    db.add(user)
    db.flush()
    db.add(character)
    db.flush()
    db.add(
        models.LlmCredential(
            id=f"credential-{suffix}",
            owner_id=user.id,
            character_id=character.id,
            provider="google",
            purpose="agent",
            model="gemini-test",
            auth_profile_id=f"profile-{suffix}",
            label="Activity runtime test key",
            encrypted_api_key="not-used-by-runtime-contract-tests",
            key_fingerprint=f"fixture-{suffix}",
            enabled=True,
        )
    )
    db.flush()
    db.add(membership)
    db.flush()
    db.add(world_character)
    db.flush()
    character_hash = world_character_contracts.character_contract_hash(character)
    world_character.character_contract_hash = character_hash
    world_character.world_contract_hash = world.contract_hash
    profile = models.WorldCommunityProfile(
        id=f"profile-{suffix}",
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
        character_contract_hash=character_hash,
        world_contract_hash=world.contract_hash,
        provider="google",
        model="gemini-test",
        credential_id=f"credential-{suffix}",
        generated_at=now,
        approved_at=now,
    )
    repertoire = models.WorldActivityRepertoire(
        id=f"repertoire-{suffix}",
        world_character_id=world_character.id,
        status="ready",
        schema_version=1,
        generator_version="test-v1",
        character_contract_hash=character_hash,
        world_contract_hash=world.contract_hash,
        community_profile_id=profile.id,
        provider="google",
        model="gemini-test",
        credential_id=f"credential-{suffix}",
        validation_summary={"candidate_count": 40},
        generated_at=now,
        approved_at=now,
    )
    db.add(profile)
    db.flush()
    db.add(repertoire)
    db.flush()
    kinds = (
        "duty",
        "rest",
        "self_care",
        "hobby",
        "exploration",
        "social",
        "maintenance",
        "challenge",
        "duty",
        "rest",
    )
    for daypart in DAYPARTS:
        for ordinal in range(1, 11):
            signature = sha256(
                f"{world_character.id}|{daypart}|{ordinal}".encode("utf-8")
            ).hexdigest()
            db.add(
                models.WorldActivityCandidate(
                    id=f"candidate-{suffix}-{daypart}-{ordinal}",
                    repertoire_id=repertoire.id,
                    daypart=daypart,
                    ordinal=ordinal,
                    activity_kind=kinds[ordinal - 1],
                    title=f"{daypart} academy activity {ordinal}",
                    activity_seed=(
                        f"During {daypart}, complete academy activity {ordinal} "
                        "and leave a concrete observation for the next scene."
                    ),
                    place_key=None,
                    social_mode="open_to_interaction",
                    canonical_signature=signature,
                    enabled=True,
                )
            )
    db.commit()
    return ReadyCharacter(
        user=user,
        character=character,
        membership=membership,
        world_character=world_character,
        profile=profile,
        repertoire=repertoire,
    )


def _seed(db: Session, *, two_characters: bool = False):
    owner = _user("world-owner")
    db.add(owner)
    db.flush()
    world = _world(owner)
    db.add(world)
    db.flush()
    first = _add_ready_character(db, world=world, suffix="a")
    second = _add_ready_character(db, world=world, suffix="b") if two_characters else None
    return world, first, second


def _add_social_event(
    db: Session,
    *,
    event_id: str,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str,
    event_type: str = "comment_created",
    occurred_at: datetime,
) -> models.SocialEvent:
    row = models.SocialEvent(
        id=event_id,
        world_id=world_id,
        actor_world_character_id=actor_world_character_id,
        target_world_character_id=target_world_character_id,
        event_type=event_type,
        result="succeeded",
        occurred_at=occurred_at,
        idempotency_key=f"fixture:{event_id}",
        schema_version="social-event-v1",
    )
    db.add(row)
    db.flush()
    return row


def _prepare(
    db: Session,
    fixture: ReadyCharacter,
    *,
    now: datetime,
    key: str = "prepare-activity-plan-a",
):
    return daily_activity_plans.prepare_activity_plan(
        db,
        references=SqlAlchemyPlanReferences(db),
        character_id=fixture.character.id,
        world_id=fixture.world_character.world_id,
        user=fixture.user,
        data=schemas.DailyActivityPlanPrepareCreate(idempotency_key=key),
        now=now,
    )


def _request(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(call())


def test_prepare_creates_four_items_without_enabling_autonomy_and_reuses() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)

        created = _prepare(db, fixture, now=now)
        replay = _prepare(db, fixture, now=now, key="different-request-key")

        assert created.reused is False
        assert replay.reused is True
        assert replay.id == created.id
        assert [item.daypart for item in created.items] == list(DAYPARTS)
        assert len({item.selected_candidate_id for item in created.items}) == 4
        assert all(item.episode is not None for item in created.items)
        assert created.current_daypart == "dawn"
        assert created.autonomous_enabled is False
        assert fixture.world_character.autonomous_enabled is False
        assert db.scalar(select(func.count(models.DailyActivityPlan.id))) == 1
        assert db.scalar(select(func.count(models.DailyActivityPlanItem.id))) == 4


def test_routines_public_uses_frozen_clock_and_writes_no_public_action() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)

        created = routines.prepare_activity_plan(
            db,
            references=SqlAlchemyPlanReferences(db),
            character_id=fixture.character.id,
            world_id=fixture.world_character.world_id,
            user=fixture.user,
            data=schemas.DailyActivityPlanPrepareCreate(
                idempotency_key="domain-clock-plan"
            ),
            clock=routines.FrozenClock(now),
        )
        replay = routines.get_activity_plan(
            db,
            references=SqlAlchemyPlanReferences(db),
            character_id=fixture.character.id,
            world_id=fixture.world_character.world_id,
            user=fixture.user,
            clock=routines.FrozenClock(now),
        )

        assert created.id == replay.id
        assert replay.reused is True
        assert db.scalar(select(func.count(models.AgentRun.id))) == 0
        assert db.scalar(select(func.count(models.Post.id))) == 0
        assert db.scalar(select(func.count(models.Comment.id))) == 0
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0


def test_owner_controlled_identity_cannot_prepare_or_reconcile_daily_plan() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)
        fixture.world_character.control_mode = "owner_controlled"
        fixture.world_character.owner_user_id = fixture.user.id
        fixture.world_character.autonomous_enabled = False
        db.commit()

        with pytest.raises(
            routines.DailyActivityPlanValidationError,
            match="owner_controlled_automation_disabled",
        ):
            routines.prepare_activity_plan(
                db,
                references=SqlAlchemyPlanReferences(db),
                character_id=fixture.character.id,
                world_id=fixture.world_character.world_id,
                user=fixture.user,
                data=schemas.DailyActivityPlanPrepareCreate(
                    idempotency_key="forged-owner-plan"
                ),
                clock=routines.FrozenClock(now),
            )

        transition = routines.reconcile_all_elapsed_routines(
            db, references=SqlAlchemyLifecycleReferences(db), clock=routines.FrozenClock(now + timedelta(days=1))
        )
        assert transition == routines.DaypartTransitionCounts(0, 0)
        assert db.scalar(select(func.count(models.DailyActivityPlan.id))) == 0
        assert db.scalar(select(func.count(models.DailyActivityPlanItem.id))) == 0
        assert db.scalar(select(func.count(models.ActivityEpisode.id))) == 0
        assert db.scalar(select(func.count(models.ActivityBeat.id))) == 0
        assert db.scalar(select(func.count(models.AgentRun.id))) == 0
        assert db.scalar(select(func.count(models.Post.id))) == 0


def test_selection_avoids_exact_repeat_for_three_recent_local_dates() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)
        dawn_signatures: list[str] = []
        for offset in range(4):
            result = _prepare(
                db,
                fixture,
                now=_utc(datetime(2026, 8, 9 + offset, 0, 5)),
                key=f"prepare-day-{offset}",
            )
            dawn_signatures.append(result.items[0].candidate_signature)

        assert len(set(dawn_signatures)) == 4


def test_daypart_windows_are_contiguous_across_dst_and_late_access_skips() -> None:
    spring = daily_activity_plans.daypart_windows(
        date(2026, 3, 8), "America/New_York"
    )
    fall = daily_activity_plans.daypart_windows(
        date(2026, 11, 1), "America/New_York"
    )
    spring_windows = list(spring.values())
    fall_windows = list(fall.values())
    assert all(
        current[1] == following[0]
        for current, following in zip(spring_windows, spring_windows[1:])
    )
    assert all(
        current[1] == following[0]
        for current, following in zip(fall_windows, fall_windows[1:])
    )
    assert spring_windows[-1][1] - spring_windows[0][0] == timedelta(hours=23)
    assert fall_windows[-1][1] - fall_windows[0][0] == timedelta(hours=25)

    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)
        late = _prepare(db, fixture, now=_utc(datetime(2026, 8, 9, 15, 0)))
        assert [item.status for item in late.items] == [
            "skipped",
            "skipped",
            "planned",
            "planned",
        ]
        assert late.items[0].episode is None
        assert late.items[1].episode is None
        assert late.current_daypart == "afternoon"


def test_invalid_repertoire_is_rejected_without_partial_plan() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)
        candidate = db.scalar(
            select(models.WorldActivityCandidate).where(
                models.WorldActivityCandidate.repertoire_id == fixture.repertoire.id
            )
        )
        assert candidate is not None
        db.delete(candidate)
        db.commit()

        with pytest.raises(
            daily_activity_plans.DailyActivityPlanValidationError,
            match="repertoire_candidate_count_invalid",
        ):
            _prepare(db, fixture, now=_utc(datetime(2026, 8, 9, 0, 30)))

        assert db.scalar(select(func.count(models.DailyActivityPlan.id))) == 0
        assert db.scalar(select(func.count(models.DailyActivityPlanItem.id))) == 0


def test_owner_api_prepares_reads_and_forbids_other_user() -> None:
    engine = _engine()
    principal: dict[str, models.User | None] = {"user": None}
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)
        outsider = _user("outsider")
        db.add(outsider)
        db.commit()
        principal["user"] = fixture.user

    app = FastAPI()
    from app.runtime.routines.composition import configure_routines_runtime
    configure_routines_runtime(app)
    app.include_router(runtime_routes.router, prefix="/api/v1")

    def get_db():
        with Session(engine) as db:
            yield db

    def current_user() -> models.User:
        assert principal["user"] is not None
        return principal["user"]

    app.dependency_overrides[api_deps.get_db] = get_db
    app.dependency_overrides[api_deps.get_current_user] = current_user
    path = "/api/v1/characters/character-a/worlds/world-a/activity-plan"

    assert _request(app, "GET", path).status_code == 404
    created = _request(
        app,
        "POST",
        f"{path}/prepare",
        json={"idempotency_key": "api-prepare-plan-a"},
    )
    assert created.status_code == 200
    assert len(created.json()["items"]) == 4
    assert created.json()["autonomous_enabled"] is False
    assert _request(app, "GET", path).json()["id"] == created.json()["id"]

    mode_path = (
        "/api/v1/characters/character-a/worlds/world-a/activity-runtime-mode"
    )
    switched = _request(
        app,
        "PATCH",
        mode_path,
        json={"activity_runtime_mode": "routine_resident_v1"},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["activity_runtime_mode"] == "routine_resident_v1"
    assert switched.json()["autonomous_enabled"] is False
    assert (
        _request(
            app,
            "PATCH",
            "/api/v1/characters/character-a/worlds/world-missing/activity-runtime-mode",
            json={"activity_runtime_mode": "legacy_resident_v1"},
        ).status_code
        == 404
    )

    principal["user"] = outsider
    assert _request(app, "GET", path).status_code == 403
    assert (
        _request(
            app,
            "PATCH",
            mode_path,
            json={"activity_runtime_mode": "legacy_resident_v1"},
        ).status_code
        == 403
    )


def test_state_contract_bounds_decay_and_rejects_excess_delta() -> None:
    changed = activity_state_contracts.apply_state_changes(
        activity_state_contracts.initial_state(),
        [
            {
                "mood": "curious",
                "mood_intensity_delta": 20,
                "energy_delta": -5,
                "social_energy_delta": 10,
                "action_note": "A reply may shape the next scene.",
            }
        ],
    )
    assert changed == {
        "mood": "curious",
        "mood_intensity": 20,
        "energy": 45,
        "social_energy": 60,
        "action_note": "A reply may shape the next scene.",
    }
    decayed = activity_state_contracts.apply_state_changes(
        changed,
        [],
        scheduled_without_source=True,
        daypart_ended=True,
    )
    assert decayed["mood"] == "neutral"
    assert decayed["mood_intensity"] == 0
    with pytest.raises(activity_state_contracts.ActivityStateValidationError):
        activity_state_contracts.apply_state_changes(
            activity_state_contracts.initial_state(),
            [
                {"energy_delta": 20},
                {"energy_delta": 20},
            ],
        )


def test_latest_due_tick_returns_only_newest_tick_and_counts_missed_work() -> None:
    start = _utc(datetime(2026, 8, 9, 10, 0))
    end = _utc(datetime(2026, 8, 9, 12, 0))
    due = activity_runtime.latest_due_tick(
        window_start=start,
        window_end=end,
        now=_utc(datetime(2026, 8, 9, 11, 40)),
        activity_interval_minutes=30,
        last_scheduled_for=start,
    )
    assert due is not None
    assert due.scheduled_for == _utc(datetime(2026, 8, 9, 11, 30))
    assert due.skipped_tick_count == 2
    assert (
        activity_runtime.latest_due_tick(
            window_start=start,
            window_end=end,
            now=end,
            activity_interval_minutes=30,
        )
        is None
    )
    with pytest.raises(
        activity_runtime.ActivityRuntimeValidationError,
        match="activity_interval_out_of_range",
    ):
        activity_runtime.latest_due_tick(
            window_start=start,
            window_end=end,
            now=start,
            activity_interval_minutes=29,
        )


def test_beat_success_applies_event_once_and_failure_releases_claim() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        world, fixture, other = _seed(db, two_characters=True)
        assert other is not None
        _add_social_event(
            db,
            event_id="event-1",
            world_id=world.id,
            actor_world_character_id=other.world_character.id,
            target_world_character_id=fixture.world_character.id,
            occurred_at=now - timedelta(minutes=5),
        )
        _add_social_event(
            db,
            event_id="event-2",
            world_id=world.id,
            actor_world_character_id=other.world_character.id,
            target_world_character_id=fixture.world_character.id,
            occurred_at=now + timedelta(minutes=55),
        )
        db.commit()
        plan = _prepare(db, fixture, now=now)
        episode_id = plan.items[0].episode.id  # type: ignore[union-attr]
        beat_claim = activity_runtime.claim_activity_beat(
            db,
            episode_id=episode_id,
            scheduled_for=now,
            trigger_kind="comment_influenced",
            idempotency_key="beat-1",
            claim_run_id="run-1",
            claim_expires_at=now + timedelta(minutes=10),
            source_event_ids=["event-1"],
            now=now,
        )
        event_claim = activity_runtime.claim_event_consumption(
            db,
            references=SqlAlchemyActivityReferences(db),
            world_id=fixture.world_character.world_id,
            consumer_world_character_id=fixture.world_character.id,
            source_social_event_id="event-1",
            target_activity_beat_id=beat_claim.row.id,
            idempotency_key="event-claim-1",
            claim_run_id="run-1",
            claim_expires_at=now + timedelta(minutes=10),
            now=now,
        )
        post = models.Post(
            id="post-1",
            author_user_id=None,
            author_character_id=fixture.character.id,
            author_name=fixture.character.name,
            title="Morning observation",
            body="A reply changed how the activity continued.",
        )
        db.add(post)
        db.commit()
        next_state = activity_state_contracts.apply_state_changes(
            activity_state_contracts.initial_state(),
            [{"mood": "curious", "mood_intensity_delta": 10}],
        )
        activity_runtime.complete_activity_beat(
            db,
            references=SqlAlchemyActivityReferences(db),
            beat_id=beat_claim.row.id,
            claim_run_id="run-1",
            source_post_id=post.id,
            state_after_snapshot=next_state,
            result_snapshot={"post_id": post.id},
            now=now + timedelta(minutes=1),
        )
        assert db.get(models.ActivityEventConsumption, event_claim.row.id).status == "applied"
        episode = db.get(models.ActivityEpisode, episode_id)
        assert episode is not None
        assert episode.status == "active"
        assert episode.last_successful_beat_id == beat_claim.row.id
        assert episode.current_state_snapshot == next_state
        with pytest.raises(
            activity_runtime.ActivityRuntimeConflictError,
            match="source_event_already_consumed",
        ):
            activity_runtime.claim_event_consumption(
                db,
                references=SqlAlchemyActivityReferences(db),
                world_id=fixture.world_character.world_id,
                consumer_world_character_id=fixture.world_character.id,
                source_social_event_id="event-1",
                target_activity_beat_id=beat_claim.row.id,
                idempotency_key="event-claim-replay",
                claim_run_id="run-replay",
                claim_expires_at=now + timedelta(minutes=20),
                now=now + timedelta(minutes=2),
            )

        failed_beat = activity_runtime.claim_activity_beat(
            db,
            episode_id=episode_id,
            scheduled_for=now + timedelta(hours=1),
            trigger_kind="comment_influenced",
            idempotency_key="beat-2",
            claim_run_id="run-2",
            claim_expires_at=now + timedelta(hours=1, minutes=10),
            source_event_ids=["event-2"],
            now=now + timedelta(hours=1),
        )
        released = activity_runtime.claim_event_consumption(
            db,
            references=SqlAlchemyActivityReferences(db),
            world_id=fixture.world_character.world_id,
            consumer_world_character_id=fixture.world_character.id,
            source_social_event_id="event-2",
            target_activity_beat_id=failed_beat.row.id,
            idempotency_key="event-claim-2",
            claim_run_id="run-2",
            claim_expires_at=now + timedelta(hours=1, minutes=10),
            now=now + timedelta(hours=1),
        )
        activity_runtime.fail_activity_beat(
            db,
            beat_id=failed_beat.row.id,
            claim_run_id="run-2",
            reason_code="provider_timeout",
            now=now + timedelta(hours=1, minutes=1),
        )
        assert db.get(models.ActivityEventConsumption, released.row.id).status == "released"
        refreshed_episode = db.get(models.ActivityEpisode, episode_id)
        assert refreshed_episode.last_successful_beat_id == beat_claim.row.id
        assert refreshed_episode.current_state_snapshot == next_state
        assert refreshed_episode.next_sequence_no == 3


def test_daypart_transition_closes_successful_episode_without_provider_work() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 5, 30))
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)
        plan = _prepare(db, fixture, now=now)
        dawn = next(item for item in plan.items if item.daypart == "dawn")
        assert dawn.episode is not None
        beat = activity_runtime.claim_activity_beat(
            db,
            episode_id=dawn.episode.id,
            scheduled_for=now,
            trigger_kind="scheduled",
            idempotency_key="daypart-beat",
            claim_run_id="daypart-run",
            claim_expires_at=now + timedelta(minutes=10),
            now=now,
        )
        post = models.Post(
            id="post-daypart",
            author_character_id=fixture.character.id,
            author_name=fixture.character.name,
            title="Before class",
            body="The dawn activity reached a concrete ending.",
        )
        db.add(post)
        db.commit()
        state = activity_state_contracts.apply_state_changes(
            activity_state_contracts.initial_state(),
            [{"mood": "curious", "mood_intensity_delta": 15}],
        )
        activity_runtime.complete_activity_beat(
            db,
            references=SqlAlchemyActivityReferences(db),
            beat_id=beat.row.id,
            claim_run_id="daypart-run",
            source_post_id=post.id,
            state_after_snapshot=state,
            result_snapshot={"post_id": post.id},
            now=now + timedelta(minutes=1),
        )

        transition = activity_runtime.close_elapsed_dayparts(
            db,
            world_character_id=fixture.world_character.id,
            now=_utc(datetime(2026, 8, 9, 6, 1)),
        )
        assert transition.completed == 1
        assert transition.skipped == 0
        item = db.get(models.DailyActivityPlanItem, dawn.id)
        episode = db.get(models.ActivityEpisode, dawn.episode.id)
        assert item is not None and item.status == "completed"
        assert episode is not None and episode.status == "completed"
        assert episode.current_state_snapshot["mood"] == "neutral"
        assert episode.completion_summary == {
            "successful_beat_count": 1,
            "successful_post_ids": [post.id],
        }


def test_scheduler_reconciles_all_elapsed_routines_without_catch_up_work() -> None:
    engine = _engine()
    plan_started_at = _utc(datetime(2026, 8, 9, 0, 30))
    reconcile_at = _utc(datetime(2026, 8, 9, 12, 1))
    with Session(engine, expire_on_commit=False) as db:
        _world_row, first, second = _seed(db, two_characters=True)
        assert second is not None
        first_plan = _prepare(db, first, now=plan_started_at, key="reconcile-first")
        second_plan = _prepare(db, second, now=plan_started_at, key="reconcile-second")

        transition = routine_post_runtime.reconcile_all_elapsed_routines(
            db,
            references=SqlAlchemyLifecycleReferences(db), now=reconcile_at,
        )

        assert transition == activity_runtime.DaypartTransitionCounts(
            completed=0,
            skipped=4,
        )
        for plan in (first_plan, second_plan):
            rows = list(
                db.scalars(
                    select(models.DailyActivityPlanItem)
                    .where(models.DailyActivityPlanItem.plan_id == plan.id)
                    .order_by(models.DailyActivityPlanItem.scheduled_start_at)
                )
            )
            assert [row.status for row in rows] == [
                "skipped",
                "skipped",
                "planned",
                "planned",
            ]
            episodes = list(
                db.scalars(
                    select(models.ActivityEpisode)
                    .where(
                        models.ActivityEpisode.plan_item_id.in_(
                            {rows[0].id, rows[1].id}
                        )
                    )
                    .order_by(models.ActivityEpisode.plan_item_id)
                )
            )
            assert len(episodes) == 2
            assert all(episode.status == "cancelled" for episode in episodes)
            assert all(
                episode.terminal_reason_code == "daypart_window_elapsed"
                for episode in episodes
            )

        replay = routine_post_runtime.reconcile_all_elapsed_routines(
            db,
            references=SqlAlchemyLifecycleReferences(db), now=reconcile_at,
        )
        assert replay == activity_runtime.DaypartTransitionCounts(0, 0)


def test_inactive_membership_interrupts_current_and_cancels_future_items() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 10, 0))
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)
        plan = _prepare(db, fixture, now=now)
        morning = next(item for item in plan.items if item.daypart == "morning")
        assert morning.episode is not None
        beat = activity_runtime.claim_activity_beat(
            db,
            episode_id=morning.episode.id,
            scheduled_for=now,
            trigger_kind="scheduled",
            idempotency_key="membership-beat",
            claim_run_id="membership-run",
            claim_expires_at=now + timedelta(minutes=10),
            now=now,
        )
        post = models.Post(
            id="post-membership",
            author_character_id=fixture.character.id,
            author_name=fixture.character.name,
            title="Morning class",
            body="The activity started before the character left the World.",
        )
        db.add(post)
        db.commit()
        activity_runtime.complete_activity_beat(
            db,
            references=SqlAlchemyActivityReferences(db),
            beat_id=beat.row.id,
            claim_run_id="membership-run",
            source_post_id=post.id,
            state_after_snapshot=activity_state_contracts.initial_state(),
            result_snapshot={"post_id": post.id},
            now=now + timedelta(minutes=1),
        )
        fixture.membership.status = "left"
        fixture.world_character.status = "inactive"
        db.commit()

        result = activity_runtime.interrupt_inactive_world_character(
            db,
            references=SqlAlchemyActivityReferences(db),
            world_character_id=fixture.world_character.id,
            now=now + timedelta(minutes=2),
        )
        assert result.interrupted == 1
        assert result.cancelled == 2
        rows = list(
            db.scalars(
                select(models.DailyActivityPlanItem)
                .where(models.DailyActivityPlanItem.plan_id == plan.id)
                .order_by(models.DailyActivityPlanItem.scheduled_start_at)
            )
        )
        assert [row.status for row in rows] == [
            "skipped",
            "interrupted",
            "cancelled",
            "cancelled",
        ]
        assert db.get(models.DailyActivityPlan, plan.id).status == "interrupted"
        replay = activity_runtime.interrupt_inactive_world_character(
            db,
            references=SqlAlchemyActivityReferences(db),
            world_character_id=fixture.world_character.id,
            now=now + timedelta(minutes=3),
        )
        assert replay == activity_runtime.WorldInterruptionCounts(0, 0)


def test_character_scrub_removes_private_p3_runtime_before_p2_setup() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 10, 0))
    with Session(engine, expire_on_commit=False) as db:
        _world_row, fixture, _other = _seed(db)
        _prepare(db, fixture, now=now)
        world_character_setup.delete_setup_data_for_characters(
            db,
            character_ids=[fixture.character.id],
        )
        db.commit()
        assert db.scalar(select(func.count(models.DailyActivityPlan.id))) == 0
        assert db.scalar(select(func.count(models.DailyActivityPlanItem.id))) == 0
        assert db.scalar(select(func.count(models.ActivityEpisode.id))) == 0
        assert db.scalar(select(func.count(models.WorldActivityRepertoire.id))) == 0
        assert db.scalar(select(func.count(models.WorldActivityCandidate.id))) == 0
        assert db.scalar(select(func.count(models.WorldCommunityProfile.id))) == 0
        assert db.get(models.WorldCharacter, fixture.world_character.id) is not None


def test_character_scrub_removes_shared_joint_activity_without_orphaning_peer_plan() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        world, first, second = _seed(db, two_characters=True)
        assert second is not None
        _prepare(db, first, now=now, key="plan-first")
        _prepare(db, second, now=now, key="plan-second")
        joint = models.JointActivity(
            id="joint-scrub",
            world_id=world.id,
            activity_seed="Compare the observatory notes together.",
            schedule_mode="flexible",
            eligible_dayparts=["evening"],
            status="accepted_unscheduled",
            version=1,
        )
        db.add(joint)
        db.flush()
        db.add_all(
            [
                models.JointActivityParticipant(
                    joint_activity_id=joint.id,
                    world_id=world.id,
                    world_character_id=first.world_character.id,
                    role="proposer",
                    participation_status="accepted",
                ),
                models.JointActivityParticipant(
                    joint_activity_id=joint.id,
                    world_id=world.id,
                    world_character_id=second.world_character.id,
                    role="acceptor",
                    participation_status="accepted",
                ),
            ]
        )
        db.commit()
        scheduled = joint_activity_scheduling.schedule_joint_activity(
            db,
            joint_activity_id=joint.id,
            local_date=date(2026, 8, 9),
            daypart="evening",
            idempotency_key="schedule-joint-scrub",
            now=now,
        )
        peer_item_id = next(
            participant.linked_daily_activity_plan_item_id
            for participant in db.scalars(
                select(models.JointActivityParticipant).where(
                    models.JointActivityParticipant.joint_activity_id == joint.id,
                    models.JointActivityParticipant.world_character_id
                    == second.world_character.id,
                )
            )
        )
        assert peer_item_id in scheduled.linked_item_ids

        world_character_setup.delete_setup_data_for_characters(
            db,
            character_ids=[first.character.id],
        )
        db.commit()

        assert db.get(models.JointActivity, joint.id) is None
        assert (
            db.scalar(
                select(func.count(models.JointActivityParticipant.joint_activity_id))
            )
            == 0
        )
        peer_item = db.get(models.DailyActivityPlanItem, peer_item_id)
        assert peer_item is not None
        assert peer_item.joint_activity_id is None
        assert (
            db.scalar(
                select(func.count(models.DailyActivityPlan.id)).where(
                    models.DailyActivityPlan.world_character_id
                    == second.world_character.id
                )
            )
            == 1
        )


def test_expired_runtime_claims_are_recoverable_after_restart() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 1, 0))
    with Session(engine, expire_on_commit=False) as db:
        world, fixture, other = _seed(db, two_characters=True)
        assert other is not None
        _add_social_event(
            db,
            event_id="expired-event",
            world_id=world.id,
            actor_world_character_id=other.world_character.id,
            target_world_character_id=fixture.world_character.id,
            occurred_at=now - timedelta(minutes=1),
        )
        db.commit()
        plan = _prepare(db, fixture, now=now)
        episode_id = plan.items[0].episode.id  # type: ignore[union-attr]
        beat = activity_runtime.claim_activity_beat(
            db,
            episode_id=episode_id,
            scheduled_for=now,
            trigger_kind="comment_influenced",
            idempotency_key="expired-beat",
            claim_run_id="expired-run",
            claim_expires_at=now + timedelta(minutes=5),
            source_event_ids=["expired-event"],
            now=now,
        )
        consumption = activity_runtime.claim_event_consumption(
            db,
            references=SqlAlchemyActivityReferences(db),
            world_id=fixture.world_character.world_id,
            consumer_world_character_id=fixture.world_character.id,
            source_social_event_id="expired-event",
            target_activity_beat_id=beat.row.id,
            idempotency_key="expired-event-claim",
            claim_run_id="expired-run",
            claim_expires_at=now + timedelta(minutes=5),
            now=now,
        )

    with Session(engine, expire_on_commit=False) as restarted:
        recovered = activity_runtime.recover_expired_claims(
            restarted, now=now + timedelta(minutes=6)
        )
        assert recovered.beats == 1
        assert recovered.consumptions == 1
        assert restarted.get(models.ActivityBeat, beat.row.id).status == "pending"
        assert (
            restarted.get(models.ActivityEventConsumption, consumption.row.id).status
            == "released"
        )


def test_joint_schedule_links_both_participants_and_claim_has_no_consumption() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        world, first, second = _seed(db, two_characters=True)
        assert second is not None
        _add_social_event(
            db,
            event_id="proposal-a",
            world_id=world.id,
            actor_world_character_id=first.world_character.id,
            target_world_character_id=second.world_character.id,
            event_type="joint_proposed",
            occurred_at=now - timedelta(minutes=2),
        )
        _add_social_event(
            db,
            event_id="acceptance-a",
            world_id=world.id,
            actor_world_character_id=second.world_character.id,
            target_world_character_id=first.world_character.id,
            event_type="joint_accepted",
            occurred_at=now - timedelta(minutes=1),
        )
        _prepare(db, first, now=now, key="plan-first")
        _prepare(db, second, now=now, key="plan-second")
        joint = models.JointActivity(
            id="joint-a",
            world_id=world.id,
            activity_seed="Review the observatory log together.",
            place_key=None,
            schedule_mode="flexible",
            eligible_dayparts=["evening"],
            status="accepted_unscheduled",
            source_proposal_event_id="proposal-a",
            source_acceptance_event_id="acceptance-a",
            version=1,
        )
        db.add(joint)
        db.flush()
        db.add_all(
            [
                models.JointActivityParticipant(
                    joint_activity_id=joint.id,
                    world_id=world.id,
                    world_character_id=first.world_character.id,
                    role="proposer",
                    participation_status="accepted",
                ),
                models.JointActivityParticipant(
                    joint_activity_id=joint.id,
                    world_id=world.id,
                    world_character_id=second.world_character.id,
                    role="acceptor",
                    participation_status="accepted",
                ),
            ]
        )
        db.commit()

        scheduled = joint_activity_scheduling.schedule_joint_activity(
            db,
            joint_activity_id=joint.id,
            local_date=date(2026, 8, 9),
            daypart="evening",
            idempotency_key="schedule-joint-a",
            now=now,
        )
        assert scheduled.scheduled is True
        assert len(scheduled.linked_item_ids) == 2
        participants = list(
            db.scalars(
                select(models.JointActivityParticipant).where(
                    models.JointActivityParticipant.joint_activity_id == joint.id
                )
            )
        )
        assert all(
            participant.linked_daily_activity_plan_item_id is not None
            for participant in participants
        )
        assert {
            db.get(
                models.DailyActivityPlanItem,
                participant.linked_daily_activity_plan_item_id,
            ).joint_activity_id
            for participant in participants
        } == {joint.id}

        first_claim = joint_activity_scheduling.claim_representation(
            db,
            joint_activity_id=joint.id,
            claimant_world_character_id=first.world_character.id,
            claim_expires_at=now + timedelta(minutes=5),
            now=now,
        )
        assert first_claim.claim.representation_status == "claimed"
        with pytest.raises(
            joint_activity_scheduling.JointActivityConflictError,
            match="representation_already_claimed",
        ):
            joint_activity_scheduling.claim_representation(
                db,
                joint_activity_id=joint.id,
                claimant_world_character_id=second.world_character.id,
                claim_expires_at=now + timedelta(minutes=5),
                now=now,
            )
        assert db.get(models.JointActivity, joint.id).status == "scheduled"
        assert all(
            db.get(
                models.DailyActivityPlanItem,
                participant.linked_daily_activity_plan_item_id,
            ).status
            == "planned"
            for participant in participants
        )

    with Session(engine, expire_on_commit=False) as restarted:
        assert (
            joint_activity_scheduling.recover_expired_representation_claims(
                restarted, now=now + timedelta(minutes=6)
            )
            == 1
        )
        second_claim = joint_activity_scheduling.claim_representation(
            restarted,
            joint_activity_id="joint-a",
            claimant_world_character_id="world-character-b",
            claim_expires_at=now + timedelta(minutes=12),
            now=now + timedelta(minutes=7),
        )
        assert second_claim.claim.claimed_by_world_character_id == "world-character-b"


def test_joint_schedule_conflict_never_links_only_one_participant() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        world, first, second = _seed(db, two_characters=True)
        assert second is not None
        first_plan = _prepare(db, first, now=now, key="plan-first")
        _prepare(db, second, now=now, key="plan-second")
        first_morning = db.get(models.DailyActivityPlanItem, first_plan.items[1].id)
        first_morning.status = "active"
        joint = models.JointActivity(
            id="joint-conflict",
            world_id=world.id,
            activity_seed="Meet before the morning lecture.",
            schedule_mode="flexible",
            eligible_dayparts=["morning"],
            status="accepted_unscheduled",
            version=1,
        )
        db.add(joint)
        db.flush()
        db.add_all(
            [
                models.JointActivityParticipant(
                    joint_activity_id=joint.id,
                    world_id=world.id,
                    world_character_id=first.world_character.id,
                    role="proposer",
                    participation_status="accepted",
                ),
                models.JointActivityParticipant(
                    joint_activity_id=joint.id,
                    world_id=world.id,
                    world_character_id=second.world_character.id,
                    role="acceptor",
                    participation_status="accepted",
                ),
            ]
        )
        db.commit()

        with pytest.raises(
            joint_activity_scheduling.JointActivityConflictError,
            match="joint_activity_schedule_conflict",
        ):
            joint_activity_scheduling.schedule_joint_activity(
                db,
                joint_activity_id=joint.id,
                local_date=date(2026, 8, 9),
                daypart="morning",
                idempotency_key="schedule-joint-conflict",
                now=now,
            )
        participants = list(
            db.scalars(
                select(models.JointActivityParticipant).where(
                    models.JointActivityParticipant.joint_activity_id == joint.id
                )
            )
        )
        assert all(
            participant.linked_daily_activity_plan_item_id is None
            for participant in participants
        )
        assert db.get(models.JointActivity, joint.id).status == "accepted_unscheduled"
