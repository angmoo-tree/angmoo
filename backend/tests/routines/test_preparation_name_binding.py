import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from sqlalchemy import select

from app.domains.routines.models.preparation import ActivityPreparationJob
from app.domains.routines.schemas.daily_generation import InitialPreparationOutput, DailyPreparationOutput
from app.domains.social.models.topics import RecommendationPreparation
from app.domains.social.schemas.recommendation import TopicGenerationResult
from app.contracts.name_binding import read_name_binding
from app.runtime.social import topic_preparation
from tests.characters.name_binding_fixture import create_profile, rename_profile
from tests.routines.test_daily_preparation import preparation_scope, output


def test_daily_names_use_accepted_snapshot_and_next_date_uses_new_name(preparation_scope):
    db, world, ready, runtime = preparation_scope
    create_profile(db, world, ready.user.id)
    ready.character.worldview = "{{char}}는 {{user}}와 게임을 즐긴다."
    ready.character.speech_style = "대화 상대: 반가워"
    db.commit()
    now = datetime.now(UTC)
    inputs = []
    async def generate(**kwargs):
        kwargs["reserve"]()
        inputs.append(kwargs["source"])
        if len(inputs) == 1:
            rename_profile(db, world.id, ready.user.id, "민수")
        plan = output()
        for item in plan.items:
            item.title = "{{user}}와 휴식"
        value = InitialPreparationOutput(daily_plan=plan,
            recommendation_topics=[dict(name="{{char}}의 게임", scope="common")]) if kwargs["initial"] else DailyPreparationOutput(daily_plan=plan)
        return value, SimpleNamespace(calls=[])
    args = dict(character_id=ready.character.id, world_id=world.id, user=ready.user, generator=generate)
    first = asyncio.run(runtime.ensure_preparation(db, **args, now=now, request_id="accepted-first"))
    assert first.plan_state == "ready", first
    assert "민식" in inputs[0]["persona"]["description"] and "{{user}}" not in inputs[0]["persona"]["description"]
    assert inputs[0]["persona"]["speech_style"] == "대화 상대: 반가워"
    job = db.scalar(select(ActivityPreparationJob).where(ActivityPreparationJob.request_id == "accepted-first"))
    assert read_name_binding(job.input_snapshot).user_display_name == "민식"
    assert all(item["title"] == "민식와 휴식" for item in job.applied_snapshot["items"])
    assert ready.character.worldview == "{{char}}는 {{user}}와 게임을 즐긴다."
    reused = asyncio.run(runtime.ensure_preparation(db, **args, now=now))
    assert reused.plan_id == first.plan_id and len(inputs) == 1
    next_date = asyncio.run(runtime.ensure_preparation(db, **args, now=now + timedelta(days=1), request_id="next-date"))
    assert next_date.plan_state == "ready", next_date
    assert "민수" in inputs[1]["persona"]["description"] and "recommendation_topics" not in inputs[1]


def test_invalid_preparation_snapshot_stops_before_ai_and_records_failure(preparation_scope, monkeypatch):
    db, world, ready, runtime = preparation_scope
    create_profile(db, world, ready.user.id)
    original_claim = runtime.store.claim
    def corrupt(db, **kwargs):
        job, token = original_claim(db, **kwargs)
        if token:
            job.input_snapshot = {key: value for key, value in job.input_snapshot.items() if key != "name_binding"}
            db.commit()
        return job, token
    monkeypatch.setattr(runtime.store, "claim", corrupt)
    async def forbidden(**kwargs):
        raise AssertionError("Damaged names must not dispatch AI")
    result = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, generator=forbidden, request_id="corrupt-names"))
    assert result.plan_state == "failed" and result.reason_code == "name_binding_missing"
    job = db.scalar(select(ActivityPreparationJob))
    assert job.state == "failed" and job.attempt_count == 0 and job.lease_expires_at is None


def test_topic_regeneration_keeps_request_names_and_raw_persona(preparation_scope):
    db, world, ready, _ = preparation_scope
    create_profile(db, world, ready.user.id)
    ready.character.worldview = "{{user}}의 동료 {{char}}."
    db.commit()
    seen = []
    async def generate(material, character_id, source):
        seen.append(source)
        rename_profile(db, world.id, ready.user.id, "Alex")
        return TopicGenerationResult(topics=[dict(name="{{user}}의 게임", scope="common")])
    args = dict(world_id=world.id, world_character_id=ready.world_character.id, owner_id=ready.user.id,
        request_id="topic-names", generator=generate)
    result = asyncio.run(topic_preparation.regenerate(db, **args))
    assert result["state"] == "ready", result
    assert seen[0]["persona"]["description"].startswith("민식의 동료")
    assert result["topics"][0]["name"] == "민식의 게임"
    record = db.scalar(select(RecommendationPreparation).where(RecommendationPreparation.world_character_id == ready.world_character.id))
    assert read_name_binding(record.request_snapshot).user_display_name == "민식"
    assert record.request_snapshot["source"]["persona"]["description"].startswith("{{user}}")
    repeated = asyncio.run(topic_preparation.regenerate(db, **args))
    assert repeated["topics"] == result["topics"] and len(seen) == 1
    # A process that exits after claim can recover the same request without
    # mixing its accepted names with the newer My Profile display name.
    record.state = "running"
    record.lease_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    recovered = asyncio.run(topic_preparation.regenerate(db, **args))
    assert recovered["state"] == "ready" and len(seen) == 2
    assert seen[1]["persona"]["description"].startswith("민식의 동료")
    assert read_name_binding(record.request_snapshot).user_display_name == "민식"


def test_daily_expired_claim_keeps_original_name_namespace(preparation_scope):
    from app.domains.world_characters.service.name_binding import resolve_name_binding
    from app.domains.world_characters.service.preparation_lock import lock_preparation_actor
    db, world, ready, runtime = preparation_scope
    create_profile(db, world, ready.user.id)
    now = datetime.now(UTC)
    names = resolve_name_binding(db, actor=ready.world_character, owner_id=ready.user.id)
    source = {"name_binding_policy": names.policy_version, "name_binding": names.to_dict(), "persona": {"description": "{{user}}"}}
    args = dict(wc_id=ready.world_character.id, world_id=world.id, target_date=now.date(),
        timezone=world.timezone, mode="initial", request_id="expired-bound-request",
        input_digest="a" * 64, now=now, lock_actor=lock_preparation_actor)
    first, first_token = runtime.store.claim(db, **args, source=source)
    first.lease_expires_at = now - timedelta(seconds=1)
    db.commit()
    rename_profile(db, world.id, ready.user.id, "Alex")
    newer = resolve_name_binding(db, actor=ready.world_character, owner_id=ready.user.id)
    second, second_token = runtime.store.claim(db, **args, source={**source, "name_binding": newer.to_dict()})
    assert first.id == second.id and first_token != second_token
    assert read_name_binding(second.input_snapshot).user_display_name == "민식"
    assert second.input_snapshot == source
