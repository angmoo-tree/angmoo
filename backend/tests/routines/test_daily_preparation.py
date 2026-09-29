"""Direct plans preserve real history and date identity without a repertoire."""
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines.schemas.daily_generation import GeneratedDailyPlan, InitialPreparationOutput
from app.domains.routines.service import daily_preparation as service
from app.domains.routines.models.plans import ActivityEpisode
from app.domains.routines.contracts.plans import PlanScope
from app.domains.routines.models.preparation import ActivityPreparationJob
from app.domains.world_characters.service.preparation_lock import lock_preparation_actor
from app.runtime.persistence.model_registration import register_models
from tests.routines.test_daily_activity_runtime import _engine, _seed, _utc


def output():
    return GeneratedDailyPlan(items=[dict(daypart=part, activity_kind="rest", title=f"{part} 휴식",
        activity_seed="주변을 살피며 쉬기", social_mode="solo", place_key=None)
        for part in ("dawn", "morning", "afternoon", "evening")])


def test_plan_rejects_duplicate_dayparts_and_empty_or_duplicate_topics():
    data = output().model_dump()
    data["items"][0]["daypart"] = "morning"
    with pytest.raises(ValidationError):
        GeneratedDailyPlan.model_validate(data)
    for topics in ([], [{"name": "books", "scope": "common"}] * 2):
        with pytest.raises(ValidationError):
            InitialPreparationOutput(daily_plan=output(), recommendation_topics=topics)


def test_initial_direct_plan_rolls_back_with_topics_and_late_windows_are_skipped():
    register_models()
    engine = _engine()
    with Session(engine) as db:
        world, ready, _ = _seed(db)
        scope = PlanScope(world, ready.membership, ready.world_character, ready.character)
        now = _utc(datetime(2026, 9, 28, 15))
        plan = service.apply_plan(db, scope=scope, output=output(), target_date=now.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Seoul')).date(),
                                  now=now, source_digest="a"*64, expected_snapshot={})
        plan_id, target = plan.id, plan.local_date
        assert [i.status for i in sorted(service.current_items(db, plan.id), key=lambda i: i.scheduled_start_at)] == ["skipped", "skipped", "planned", "planned"]
        assert plan.repertoire_id is None
        assert len(list(db.scalars(select(ActivityEpisode)))) == 2
        db.rollback()  # A later Topic failure rolls back all pending plan writes.
        assert service.current_plan(db, ready.world_character.id, target) is None
        assert not list(db.scalars(select(ActivityEpisode)))
    engine.dispose()


def test_invalid_place_and_fixed_activity_changes_are_rejected():
    plan = output()
    plan.items[0].place_key = "other-world"
    with pytest.raises(service.PreparationConflict, match="place_invalid"):
        service.validate_plan(plan, allowed_places={}, fixed_items=[])
    plan.items[0].place_key = None
    fixed = plan.items[0].model_dump()
    fixed["title"] = "이미 완료된 일과"
    with pytest.raises(service.PreparationConflict, match="fixed_item_changed"):
        service.validate_plan(plan, allowed_places={}, fixed_items=[fixed])


def test_durable_budget_and_failed_job_do_not_reset_on_reclaim():
    register_models()
    engine = _engine()
    with Session(engine) as db:
        world, ready, _ = _seed(db)
        now = datetime.now(UTC)
        kwargs = dict(wc_id=ready.world_character.id, world_id=world.id, target_date=now.date(),
                      timezone="Asia/Seoul", mode="daily", request_id="automatic-date", source={}, input_digest="a"*64, now=now, lock_actor=lock_preparation_actor)
        job, token = service.claim(db, **kwargs)
        for _ in range(4):
            service.reserve_attempt(db, job.id, token)
        with pytest.raises(service.PreparationConflict, match="attempts_exhausted"):
            service.reserve_attempt(db, job.id, token)
        service.finish_failure(db, job.id, token, "provider_timeout", retry_at=now+timedelta(minutes=10))
        again, token2 = service.claim(db, **kwargs)
        assert token2 is None and again.attempt_count == 4 and again.state == "failed"
    engine.dispose()


@pytest.fixture
def preparation_scope(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", True)
    from app.runtime import daily_preparation as runtime
    from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
    from app.domains.worlds.models import WorldRole
    from app.domains.social.service.recommendation_topics import mark_new_subject
    register_models()
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        world, ready, _ = _seed(db)
        world.owner_user_id = ready.user.id
        db.add(WorldRole(id="role", world_id=world.id, role_key="student", name="학생"))
        mark_new_subject(db, world_id=world.id, world_character_id=ready.world_character.id)
        db.commit()
        material = CredentialMaterial("credential-a", "google", "gemini-3.1-flash-lite", "fake",
            CredentialPurpose.WORLD_CHARACTER_SETUP_LLM, "unused")
        monkeypatch.setattr(runtime.CredentialResolver, "resolve_llm_credential", lambda *a, **k: material)
        yield db, world, ready, runtime
    engine.dispose()


def test_initial_application_reuse_and_lost_topics_require_user(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    from sqlalchemy import delete
    from app.domains.social.models.topics import RecommendationTopicSource
    db, world, ready, runtime = preparation_scope
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs["initial"]); kwargs["reserve"]()
        return InitialPreparationOutput(daily_plan=output(), recommendation_topics=[dict(name="마법", scope="common")]), SimpleNamespace(calls=[])
    args = dict(character_id=ready.character.id, world_id=world.id, user=ready.user, generator=generate)
    first = asyncio.run(runtime.ensure_preparation(db, **args, request_id="first-request"))
    assert first.plan_state == "ready", first
    assert first.topic_state == "ready"
    reused = asyncio.run(runtime.ensure_preparation(db, **args))
    assert reused.plan_id == first.plan_id and calls == [True]
    db.execute(delete(RecommendationTopicSource).where(RecommendationTopicSource.source_key == ready.world_character.id)); db.commit()
    lost = asyncio.run(runtime.ensure_preparation(db, **args))
    assert lost.topic_state == "needs_user_action" and calls == [True]


def test_invalid_output_does_not_apply_either_result(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    db, world, ready, runtime = preparation_scope
    async def generate(**kwargs):
        kwargs["reserve"]()
        plan = output(); plan.items[0].place_key = "missing-place"
        return InitialPreparationOutput(daily_plan=plan, recommendation_topics=[dict(name="마법", scope="common")]), SimpleNamespace(calls=[])
    result = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, request_id="bad-output", generator=generate))
    assert result.plan_state == "failed" and result.reason_code == "daily_plan_place_invalid"
    assert result.plan_id is None and result.topic_state == "pending"


def test_different_request_ids_cannot_start_duplicate_generation(preparation_scope):
    db, world, ready, _ = preparation_scope
    now = datetime.now(UTC)
    args = dict(wc_id=ready.world_character.id, world_id=world.id, target_date=now.date(),
                timezone="Asia/Seoul", mode="daily", source={}, input_digest="a"*64, now=now, lock_actor=lock_preparation_actor)
    job, token = service.claim(db, **args, request_id="request-one")
    second, token2 = service.claim(db, **args, request_id="request-two")
    assert token and token2 is None and second.id == job.id


def test_provider_separates_initial_and_daily_instructions(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.domains.routines import client
    calls = []
    async def capture(**kwargs):
        calls.append(kwargs)
        return output()
    monkeypatch.setattr(client.direct_llm, "generate_json", capture)
    material = SimpleNamespace(reveal=lambda: "test", credential_id="test", fingerprint="fake", provider="google", model="gemini-3.1-flash-lite", thinking_level="high")
    for initial in (True, False):
        asyncio.run(client.generate_daily_preparation(material=material, character_id="fixture", source={},
            initial=initial, reserve=lambda: None, reserve_json_retry=lambda: None))
    assert "recommendation_topics" in calls[0]["system_prompt"]
    assert "recommendation_topics" not in calls[1]["system_prompt"]
    assert "recommendation_topics" not in str(calls[1]["response_schema"])
    assert all(c["sdk_attempts"] == 1 for c in calls)


def test_late_persona_change_discards_both_outputs(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    db, world, ready, runtime = preparation_scope
    async def generate(**kwargs):
        kwargs["reserve"]()
        ready.character.worldview = "수정한 캐릭터 설명"
        db.commit()
        return InitialPreparationOutput(daily_plan=output(), recommendation_topics=[dict(name="독서", scope="common")]), SimpleNamespace(calls=[])
    result = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, request_id="source-changed", generator=generate))
    assert result.plan_id is None and result.topic_state == "pending"
    assert result.reason_code == "preparation_source_changed"


def test_manual_failure_keeps_valid_plan_and_source_topics(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    from app.runtime.social.topic_preparation import read_topics
    db, world, ready, runtime = preparation_scope
    async def good(**kwargs):
        kwargs["reserve"]()
        return InitialPreparationOutput(daily_plan=output(), recommendation_topics=[dict(name="독서", scope="common")]), SimpleNamespace(calls=[])
    args = dict(character_id=ready.character.id, world_id=world.id, user=ready.user)
    one = asyncio.run(runtime.ensure_preparation(db, **args, request_id="initial-good", generator=good))
    db.expire_all()
    assert read_topics(db, world_id=world.id, owner_id=ready.user.id, world_character_id=ready.world_character.id)["state"] == "ready"
    db.rollback()
    async def bad(**kwargs):
        kwargs["reserve"]()
        raise ValueError("synthetic-invalid")
    two = asyncio.run(runtime.ensure_preparation(db, **args, request_id="manual-bad", generator=bad))
    assert two.plan_id == one.plan_id and two.plan_state == "ready"
    assert two.request_state == "failed" and two.topic_state == "ready"
    three = asyncio.run(runtime.ensure_preparation(db, **args, generator=bad))
    assert three.attempt_count == two.attempt_count


def test_file_sqlite_parallel_claims_admit_one_provider(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata
    engine = create_engine("sqlite:///" + str(tmp_path / "claims.sqlite3"), connect_args={"timeout": 5})
    build_sqlite_baseline_metadata().create_all(engine)
    with Session(engine) as db:
        world, ready, _ = _seed(db)
        ids = world.id, ready.world_character.id
    gate = Barrier(2)
    def claim(index):
        with Session(engine, expire_on_commit=False) as db:
            gate.wait()
            job, token = service.claim(db, wc_id=ids[1], world_id=ids[0], target_date=datetime.now(UTC).date(),
                timezone="Asia/Seoul", mode="daily", request_id=f"parallel-{index}", source={}, input_digest="a"*64,
                now=datetime.now(UTC), lock_actor=lock_preparation_actor)
            return job.id, token
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(claim, [1, 2]))
    assert rows[0][0] == rows[1][0]
    assert sum(token is not None for _, token in rows) == 1
    engine.dispose()


def test_daily_preparation_http_get_is_read_only_and_owner_is_required(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    import httpx
    from fastapi import FastAPI
    from app.api.identity_dependencies import get_current_user
    from app.database import get_db
    from app.domains.routines.router import router
    db, world, ready, runtime = preparation_scope
    app = FastAPI(); app.include_router(router, prefix="/characters")
    user = SimpleNamespace(id=ready.user.id)
    calls = []
    async def ensure(db, **kwargs):
        calls.append(kwargs)
        return runtime.read_preparation(db, character_id=kwargs["character_id"], world_id=kwargs["world_id"], user=kwargs["user"])
    app.state.daily_preparation = SimpleNamespace(read=runtime.read_preparation, ensure=ensure)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            path = f"/characters/{ready.character.id}/worlds/{world.id}/daily-preparation"
            for _ in range(2): assert (await client.get(path)).status_code == 200
            assert calls == [] and not list(db.scalars(select(ActivityPreparationJob)))
            assert (await client.post(path, json={"request_id":"explicit-click"})).status_code == 200
            assert len(calls) == 1
            user.id = "foreign"
            assert (await client.get(path)).status_code == 403
            assert (await client.post(path, json={"request_id":"foreign-click"})).status_code == 403
    asyncio.run(run())


def enable_automatic(db, ready, start="22:00", end="03:00"):
    from app.domains.world_characters.models import CharacterActiveWorld
    from app.domains.routines.models.resident import AgentActivitySetting
    ready.world_character.autonomous_enabled = True
    ready.world_character.activity_runtime_mode = "routine_resident_v1"
    db.add(CharacterActiveWorld(character_id=ready.character.id, world_character_id=ready.world_character.id,
        selected_at=datetime.now(UTC), idempotency_key="selected-test"))
    db.add(AgentActivitySetting(character_id=ready.character.id, auto_enabled=True,
        active_hours_start=start, active_hours_end=end))
    db.commit()


def test_automatic_midnight_same_date_reuse_and_hours(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    from app.domains.routines.schemas.daily_generation import DailyPreparationOutput
    db, world, ready, runtime = preparation_scope
    enable_automatic(db, ready)
    # Future deterministic date keeps durable lease valid against the real clock.
    date = datetime.now(UTC).date() + timedelta(days=7)
    local = datetime.combine(date, datetime.min.time())
    calls = []
    async def generate(**kwargs):
        kwargs["reserve"](); calls.append(kwargs["initial"])
        value = dict(daily_plan=output())
        return (InitialPreparationOutput(**value, recommendation_topics=[dict(name="독서", scope="common")])
                if kwargs["initial"] else DailyPreparationOutput(**value)), SimpleNamespace(calls=[])
    args = dict(character_id=ready.character.id, world_id=world.id, user=ready.user, generator=generate)
    async def at(hours):
        return await runtime.ensure_preparation(db, **args, now=_utc(local+timedelta(hours=hours)))
    assert asyncio.run(at(21)).plan_state == "pending" and calls == []
    first = asyncio.run(at(22)); assert first.plan_state == "ready", first
    assert asyncio.run(at(23)).plan_id == first.plan_id and calls == [True]
    second = asyncio.run(at(24)); assert second.plan_state == "ready", second
    assert second.plan_id != first.plan_id and calls == [True, False]
    assert asyncio.run(at(26)).plan_id == second.plan_id
    assert asyncio.run(at(46)).plan_id == second.plan_id and calls == [True, False]
    ready.world_character.autonomous_enabled = False; db.commit()
    assert asyncio.run(at(48)).plan_state == "pending" and len(calls) == 2
    ready.world_character.autonomous_enabled = True; db.commit()
    assert asyncio.run(at(51)).plan_state == "pending" and len(calls) == 2 # 03:00 outside
    assert asyncio.run(at(70)).plan_state == "ready" and calls == [True, False, False]


def test_off_during_generation_discards_result_and_failure_does_not_loop(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    from app.domains.world_characters.models import WorldCharacter
    db, world, ready, runtime = preparation_scope
    enable_automatic(db, ready, "07:00", "17:00")
    at = _utc(datetime.combine(datetime.now(UTC).date()+timedelta(days=7), datetime.min.time())+timedelta(hours=10))
    calls = []
    async def generate(**kwargs):
        kwargs["reserve"](); calls.append(1)
        db.get(WorldCharacter, ready.world_character.id).autonomous_enabled = False; db.commit()
        return InitialPreparationOutput(daily_plan=output(), recommendation_topics=[dict(name="독서", scope="common")]), SimpleNamespace(calls=[])
    args = dict(character_id=ready.character.id, world_id=world.id, user=ready.user, generator=generate, now=at)
    first = asyncio.run(runtime.ensure_preparation(db, **args))
    assert first.plan_id is None and first.reason_code == "preparation_scope_changed"
    ready.world_character.autonomous_enabled = True; db.commit()
    for _ in range(3): assert asyncio.run(runtime.ensure_preparation(db, **args)).plan_state == "failed"
    assert calls == [1]


def test_manual_plan_revision_preserves_completed_item_and_episode(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    from app.domains.routines.schemas.daily_generation import DailyPreparationOutput
    db, world, ready, runtime = preparation_scope
    date = datetime.now(UTC).date()+timedelta(days=7)
    at = _utc(datetime.combine(date, datetime.min.time())+timedelta(hours=10))
    async def generate(**kwargs):
        kwargs["reserve"]()
        value = output()
        for item in value.items:
            if item.daypart == "afternoon": item.title = "수정한 오후 일과"
        from app.domains.routines.schemas.daily_generation import preparation_output_type
        generated = kwargs["source"].get("generated_dayparts", [item.daypart for item in value.items])
        fields = {"daily_plan": {"items": [item.model_dump() for item in value.items if item.daypart in generated]}}
        if kwargs["initial"]:
            fields["recommendation_topics"] = [dict(name="독서", scope="common")]
        return preparation_output_type(kwargs["source"], initial=kwargs["initial"])(**fields), SimpleNamespace(calls=[])
    args = dict(character_id=ready.character.id, world_id=world.id, user=ready.user, generator=generate, now=at)
    first = asyncio.run(runtime.ensure_preparation(db, **args, request_id="create-plan"))
    items = service.current_items(db, first.plan_id)
    morning = next(i for i in items if i.daypart == "morning")
    morning.status = "completed"; db.commit()
    episode_id = db.scalar(select(ActivityEpisode.id).where(ActivityEpisode.plan_item_id==morning.id))
    second = asyncio.run(runtime.ensure_preparation(db, **args, request_id="revise-plan", expected_version=first.plan_version))
    assert second.plan_state == "ready" and second.plan_version == first.plan_version+1, second
    current = service.current_items(db, first.plan_id)
    assert len(current) == 4
    assert next(i for i in current if i.daypart=="morning").id == morning.id
    assert db.get(ActivityEpisode, episode_id) is not None
    repeated = asyncio.run(runtime.ensure_preparation(db, **args, request_id="revise-plan", expected_version=first.plan_version))
    assert repeated.plan_version == second.plan_version and repeated.attempt_count == second.attempt_count


@pytest.mark.parametrize("action", ["repost", "follow", "unfollow"])
def test_new_policy_rejects_unexecuted_old_checkpoint_actions(preparation_scope, action):
    import asyncio
    from types import SimpleNamespace
    from app.runtime.autonomous_activity.social_lane import SocialLane
    db, world, ready, runtime = preparation_scope
    lane = object.__new__(SocialLane)
    lane.ctx = SimpleNamespace(db=db, run_id="nonexistent-run", character=ready.character)
    lane.lane = "feed"
    executed = []
    lane.action_executor = lambda *a, **k: executed.append(k)
    state = {"identity":{"contract_version":2}, "decision":{"decisions":[{"action":action, "target_id":"target"}]},
             "lane_data":{"target":{"post_id":"post"}}}
    with pytest.raises(ValueError, match="activity_action_disabled"):
        asyncio.run(lane.execute(state))
    assert executed == []


def test_direct_plan_joint_scheduling_keeps_two_actor_and_claim_contract(monkeypatch):
    from tests.routines import test_daily_activity_runtime as existing
    from zoneinfo import ZoneInfo
    def prepare(db, fixture, *, now, key):
        world = db.get(existing.models.World, fixture.world_character.world_id)
        plan = service.apply_plan(db, scope=PlanScope(world, fixture.membership, fixture.world_character, fixture.character),
            output=output(), target_date=now.astimezone(ZoneInfo(world.timezone)).date(), now=now,
            source_digest="b"*64, expected_snapshot={})
        db.commit()
        return plan
    monkeypatch.setattr(existing, "_prepare", prepare)
    existing.test_joint_schedule_links_both_participants_and_claim_has_no_consumption()


def test_initial_plan_cannot_overwrite_concurrent_manual_topics(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    from app.domains.social.models.topics import RecommendationPreparation
    from app.domains.social.service.recommendation_topics import replace_source_topics
    db, world, ready, runtime = preparation_scope
    async def generate(**kwargs):
        kwargs["reserve"]()
        prep = db.scalar(select(RecommendationPreparation).where(
            RecommendationPreparation.source_key == ready.world_character.id))
        replace_source_topics(db, world_id=world.id, world_character_id=ready.world_character.id,
                              topics=[("사용자가 다시 만든 주제", "common")])
        prep.request_id, prep.applied_digest, prep.state = "manual-topic", "new-topic-generation", "ready"
        db.commit()
        return InitialPreparationOutput(daily_plan=output(), recommendation_topics=[dict(name="뒤늦은 최초 주제", scope="common")]), SimpleNamespace(calls=[])
    result = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, request_id="first-plan", generator=generate))
    assert result.plan_id is None and result.topic_state == "ready"
    assert result.reason_code == "preparation_topics_changed"
    db.expire_all()
    prep = db.scalar(select(RecommendationPreparation).where(
        RecommendationPreparation.source_key == ready.world_character.id))
    assert prep.applied_digest == "new-topic-generation"


def test_manual_revision_cannot_overwrite_new_episode_state(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    from app.domains.routines.schemas.daily_generation import DailyPreparationOutput
    db, world, ready, runtime = preparation_scope
    date = datetime.now(UTC).date()+timedelta(days=7)
    at = _utc(datetime.combine(date, datetime.min.time())+timedelta(hours=10))
    async def initial(**kwargs):
        kwargs["reserve"]()
        return InitialPreparationOutput(daily_plan=output(), recommendation_topics=[dict(name="독서", scope="common")]), SimpleNamespace(calls=[])
    args = dict(character_id=ready.character.id, world_id=world.id, user=ready.user, now=at)
    first = asyncio.run(runtime.ensure_preparation(db, **args, request_id="before-scene", generator=initial))
    item = next(i for i in service.current_items(db, first.plan_id) if i.daypart == "morning")
    episode = db.scalar(select(ActivityEpisode).where(ActivityEpisode.plan_item_id == item.id))
    original_version = episode.version
    async def during_scene(**kwargs):
        kwargs["reserve"]()
        episode.version += 1
        episode.current_state_snapshot = {"actual_scene": "newly committed state"}
        db.commit()
        return DailyPreparationOutput(daily_plan=output()), SimpleNamespace(calls=[])
    second = asyncio.run(runtime.ensure_preparation(db, **args, request_id="during-scene", generator=during_scene))
    assert second.plan_id == first.plan_id and second.plan_version == first.plan_version
    assert second.request_state == "failed"
    db.expire_all()
    assert db.get(ActivityEpisode, episode.id).version == original_version + 1
    assert db.get(ActivityEpisode, episode.id).current_state_snapshot["actual_scene"] == "newly committed state"


def test_character_cleanup_removes_private_preparation_and_plan(preparation_scope):
    import asyncio
    from types import SimpleNamespace
    from app.runtime.world_characters.cleanup import delete_setup_data_for_characters
    from app.domains.routines.models.preparation import ActivityPreparationJob
    from app.domains.routines.models.plans import DailyActivityPlan
    db, world, ready, runtime = preparation_scope
    async def generate(**kwargs):
        kwargs["reserve"]()
        return InitialPreparationOutput(daily_plan=output(), recommendation_topics=[dict(name="독서", scope="common")]), SimpleNamespace(calls=[])
    result = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, request_id="before-delete", generator=generate))
    assert result.plan_id is not None
    assert db.scalar(select(ActivityPreparationJob.id)) is not None
    delete_setup_data_for_characters(db, character_ids=[ready.character.id])
    db.commit()
    assert db.scalar(select(ActivityPreparationJob.id)) is None
    assert db.scalar(select(DailyActivityPlan.id).where(DailyActivityPlan.id == result.plan_id)) is None
