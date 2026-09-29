"""New ordinary outputs, immutable preserved slots and accepted-request readers."""
import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.domains.routines.client import generate_daily_preparation, preparation_response_schema
from app.domains.routines.contracts.plans import PlanScope
from app.domains.routines.models.preparation import ActivityPreparationJob
from app.domains.routines.schemas.daily_generation import (
    DAYPARTS, GENERATION_CONTRACT, InitialPreparationOutput, OrdinaryGeneratedPlan,
    preparation_output_type,
)
from app.domains.routines.service import daily_preparation as store
from app.domains.social.models.topics import RecommendationPreparation
from app.domains.social.schemas.recommendation import TopicGenerationResult
from app.domains.social.service.recommendation_topics import replace_source_topics
from app.domains.world_characters.service.preparation_lock import lock_preparation_actor
from tests.routines.test_daily_preparation import output, preparation_scope
from tests.routines.test_daily_activity_runtime import _utc


def time_for_test():
    return _utc(datetime.combine(datetime.now(UTC).date() + timedelta(days=7), datetime.min.time()) + timedelta(minutes=30))


def new_output(source, *, initial=False):
    value = {"daily_plan": {"items": [item.model_dump() for item in output().items
                                     if item.daypart in source["generated_dayparts"]]}}
    if initial:
        value["recommendation_topics"] = [{"name": "책 이야기", "scope": "common"}]
    return preparation_output_type(source, initial=initial)(**value)


def save_plan(db, world, ready, now):
    return store.apply_plan(db, scope=PlanScope(world, ready.membership, ready.world_character, ready.character),
        output=output(), target_date=now.astimezone(ZoneInfo(world.timezone)).date(),
        now=now, source_digest="a" * 64, expected_snapshot={})


def topics_ready(db, world, ready):
    replace_source_topics(db, world_id=world.id, world_character_id=ready.world_character.id,
        topics=[("책 이야기", "common")])
    prep = db.scalar(select(RecommendationPreparation).where(RecommendationPreparation.source_key == ready.world_character.id))
    prep.state, prep.applied_digest = "ready", "previous-topics"


@pytest.mark.parametrize("preserved", range(5))
def test_only_unpreserved_slots_are_generated_and_all_originals_survive(preparation_scope, preserved):
    db, world, ready, runtime = preparation_scope
    now = time_for_test()
    plan = save_plan(db, world, ready, now)
    items = sorted(store.current_items(db, plan.id), key=lambda row: DAYPARTS.index(row.daypart))
    for row in items[:preserved]:
        row.is_user_pinned = True
        row.title = "원본 {{user}} 이름 유지"
    topics_ready(db, world, ready)
    db.commit()
    original = {row.daypart: (row.id, row.title, row.version, row.scheduled_start_at, row.scheduled_end_at) for row in items[:preserved]}
    calls = []
    async def generate(**kwargs):
        kwargs["reserve"]()
        source = kwargs["source"]
        calls.append(source)
        assert source["generated_dayparts"] == list(DAYPARTS[preserved:])
        return new_output(source), SimpleNamespace(calls=[{"status": "succeeded"}])
    result = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, request_id=f"preserve-{preserved}", now=now, generator=generate))
    assert result.plan_state == "ready", result
    assert len(calls) == (0 if preserved == 4 else 1)
    assert result.plan_version == (1 if preserved == 4 else 2)
    db.expire_all()
    final = store.current_items(db, plan.id)
    assert len(final) == 4
    for row in final:
        if row.daypart in original:
            assert (row.id, row.title, row.version, row.scheduled_start_at, row.scheduled_end_at) == original[row.daypart]
    if calls:
        job = db.scalar(select(ActivityPreparationJob).where(ActivityPreparationJob.request_id == f"preserve-{preserved}"))
        assert job.input_snapshot["generation_contract"] == GENERATION_CONTRACT
        assert job.state == "ready"


def test_all_preserved_initial_uses_topics_only_and_keeps_plan_unchanged(preparation_scope):
    db, world, ready, runtime = preparation_scope
    now = time_for_test()
    plan = save_plan(db, world, ready, now)
    for item in store.current_items(db, plan.id):
        item.is_user_pinned = True
    db.commit()
    before = store.plan_snapshot(db, plan)
    seen = []
    async def forbidden(**kwargs):
        pytest.fail("No daily provider request is required")
    async def topic_generator(material, character_id, source, *, tracker):
        tracker.next_provider_call_order()
        seen.append(source)
        return TopicGenerationResult(topics=[{"name": "고양이 간식", "scope": "common"}])
    result = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, request_id="topics-only-initial", now=now, generator=forbidden, topic_generator=topic_generator))
    assert result.topic_state == "ready" and result.plan_version == 1, result
    assert len(seen) == 1 and set(seen[0]) == {"persona", "world"}
    db.expire_all()
    assert store.plan_snapshot(db, db.get(type(plan), plan.id)) == before
    job = db.scalar(select(ActivityPreparationJob).where(ActivityPreparationJob.request_id == "topics-only-initial"))
    assert job.mode == "initial" and job.attempt_count == 1 and job.state == "ready"
    assert job.input_snapshot["generated_dayparts"] == []


@pytest.mark.parametrize("field,value", [("activity_kind", "joint_activity"), ("social_mode", "joint")])
def test_reserved_enum_is_rejected_in_new_request_and_retained_in_legacy_reader(field, value):
    raw = output().model_dump()
    raw["items"][0][field] = value
    with pytest.raises(ValidationError):
        OrdinaryGeneratedPlan.model_validate(raw)
    assert InitialPreparationOutput(daily_plan=raw, recommendation_topics=[{"name": "책 이야기", "scope": "common"}])
    schema = preparation_response_schema({"generation_contract": GENERATION_CONTRACT, "generated_dayparts": ["afternoon", "evening"]}, initial=False)
    array = schema["properties"]["daily_plan"]["properties"]["items"]
    assert array["minItems"] == array["maxItems"] == 2
    props = array["items"]["properties"]
    assert props["daypart"]["enum"] == ["afternoon", "evening"]
    assert "joint_activity" not in props["activity_kind"]["enum"]
    assert "joint" not in props["social_mode"]["enum"]


def test_provider_schema_and_validator_use_the_same_daypart_partition(monkeypatch):
    from app.integrations import direct_llm
    source = {"generation_contract": GENERATION_CONTRACT, "generated_dayparts": ["evening"],
              "fixed_items": [item.model_dump() for item in output().items if item.daypart != "evening"], "allowed_places": {}}
    async def generate(**kwargs):
        assert "fixed_items are" in kwargs["system_prompt"]
        assert "recommendation_topics" not in kwargs["response_schema"]["properties"]
        assert kwargs["response_schema"]["properties"]["daily_plan"]["properties"]["items"]["maxItems"] == 1
        good = new_output(source).model_dump()
        assert kwargs["validator"](good)
        bad = output().model_dump()
        with pytest.raises(store.PreparationConflict, match="dayparts_mismatch"):
            kwargs["validator"]({"daily_plan": bad})
        return kwargs["validator"](good)
    monkeypatch.setattr(direct_llm, "generate_json", generate)
    material = SimpleNamespace(reveal=lambda: "synthetic", credential_id="test", provider="google", model="gemini-3.1-flash-lite", fingerprint="test", thinking_level="high")
    value, _ = asyncio.run(generate_daily_preparation(material=material, character_id="test", source=source,
        initial=False, reserve=lambda: None, reserve_json_retry=lambda: None))
    assert len(value.daily_plan.items) == 1


def test_legacy_waiting_job_reuses_its_original_schema_digest_and_source(preparation_scope):
    db, world, ready, runtime = preparation_scope
    now = time_for_test()
    scope = runtime._scope(db, ready.character.id, world.id, ready.user)
    source, digest, _, _ = runtime._source(db, scope, now, generation_contract=None)
    job, token = store.claim(db, wc_id=ready.world_character.id, world_id=world.id,
        target_date=date.fromisoformat(source["local_date"]), timezone=world.timezone,
        mode="initial", request_id="legacy-waiting", source=source, input_digest=digest, now=now,
        lock_actor=lock_preparation_actor)
    store.finish_failure(db, job.id, token, "old-provider-unavailable", retry_at=now-timedelta(seconds=1))
    db.expire_all()
    assert db.get(ActivityPreparationJob, job.id).state == "waiting"
    db.commit()
    seen = []
    async def generate(**kwargs):
        kwargs["reserve"]()
        seen.append(kwargs["source"])
        assert "generation_contract" not in kwargs["source"]
        return InitialPreparationOutput(daily_plan=output(), recommendation_topics=[{"name": "책 이야기", "scope": "common"}]), SimpleNamespace(calls=[])
    result = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, request_id="legacy-waiting", now=now, generator=generate))
    assert result.plan_state == "ready" and len(seen) == 1, result
    db.expire_all()
    assert db.get(ActivityPreparationJob, job.id).input_digest == digest


def test_new_plan_cannot_overwrite_changed_preserved_window(preparation_scope):
    db, world, ready, runtime = preparation_scope
    now = time_for_test()
    plan = save_plan(db, world, ready, now)
    fixed = store.current_items(db, plan.id)[0]
    fixed.is_user_pinned = True
    topics_ready(db, world, ready)
    db.commit()
    async def generate(**kwargs):
        kwargs["reserve"]()
        fixed.scheduled_end_at += timedelta(minutes=1)
        db.commit()
        return new_output(kwargs["source"]), SimpleNamespace(calls=[])
    result = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, request_id="changed-fixed-window", now=now, generator=generate))
    assert result.plan_version == 1 and result.request_state == "failed"
    assert result.request_reason_code == "preparation_source_changed"
