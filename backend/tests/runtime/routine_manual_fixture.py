"""Synthetic user replies through the real writer, claim and delivery boundaries."""
import json
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from model_fixture_support import models
from relationships.test_social_event_runtime import _character
from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc
from memory.test_activity_situation_receipt import enabled
from app.domains.social.contracts.writes import OwnerReplyCommand
from app.providers.contracts import ProviderCapabilities, ProviderResponse, ProviderUsage
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork
from app.runtime.routine_posts.sqlalchemy_runtime import prepare_routine_activity
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.routine_resume import freeze_prepared
from app.runtime.autonomous_activity.routine_sources import source_manifest
from app.runtime.autonomous_activity.social_lane import plain
from app.domains.routine_posts.service.evidence import build_routine_prompt_context


@pytest.fixture
def manual_routine(monkeypatch, deny_external_network, request):
    from app.integrations import direct_llm
    # Each isolated DB also owns an isolated quota history; submission is real.
    direct_llm._RATE_LIMITER._buckets.clear()
    from app.config import settings
    # This fixture owns an approved legacy repertoire; no preparation provider.
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    engine = _engine()
    with Session(engine, expire_on_commit=False, autoflush=False) as db:
        seeded = _seed(db)
        now = _utc(datetime(2026, 8, 10, 10, 5))
        from app.domains.relationships.service.policy_activation import activate_policy
        activate_policy(db, world_id=seeded.world.id, now=now-timedelta(days=1))
        db.add(models.InstallationIdentity(singleton_key="local-installation",
            installation_id="routine-source-test", owner_user_id=seeded.user.id,
            bootstrap_state="claimed", local_label="test", claimed_at=now))
        db.get(models.WorldMembership, seeded.world_character.membership_id).role = "owner"
        character = _character(seeded.user, "routine-source-owner")
        db.add(character); db.flush()
        owner = models.WorldCharacter(id="routine-source-owner", world_id=seeded.world.id,
            character_id=character.id, membership_id=seeded.world_character.membership_id,
            role_key="student", status="active", control_mode="owner_controlled",
            owner_user_id=seeded.user.id, autonomous_enabled=False,
            activity_runtime_mode="legacy_resident_v1", feed_runtime_mode="legacy_latest_v1",
            local_profile={}, character_contract_hash="a"*64, world_contract_hash=seeded.world.contract_hash)
        db.add(owner); db.flush()
        db.add(models.CharacterActiveWorld(character_id=character.id, world_character_id=owner.id,
            selected_at=now, idempotency_key="routine-source-owner-active", version=1))
        from app.runtime.world_characters.creation_configuration import initialize_created_world_character
        initialize_created_world_character(db, character=character, world_character=owner)
        root = models.Post(id="routine-source-root", author_name=seeded.character.name,
            author_character_id=seeded.character.id, author_world_character_id=seeded.world_character.id,
            world_id=seeded.world.id, activity_episode_id=seeded.morning_episode.id,
            title="Morning practice", body="I am beginning a new experiment.", created_at=now-timedelta(minutes=4))
        db.add(root); db.commit()
        write = SqlAlchemySocialWriteUnitOfWork(db).create_owner_reply(OwnerReplyCommand(
            world_id=seeded.world.id, current_user_id=seeded.user.id, target_post_id=root.id,
            idempotency_key="routine-source-reply", body="Try a cooler temperature for the next experiment."))
        candidate = db.get(models.OwnerManualInboxCandidate, write.delivery.inbox_candidate_id)
        reply = db.get(models.Post, candidate.source_reply_post_id)
        candidate.created_at = reply.created_at = now-timedelta(minutes=2)
        db.commit()
        ctx = _resident_context(db, seeded, run_id="routine-source-run", now=now)
        prepared = None
        if getattr(request, "param", True):
            prepared = prepare_routine_activity(ctx, observe_inputs=False)
            assert not isinstance(prepared, dict), prepared
            assert prepared.claimed_manual_source_ids == [f"manual-inbox:{candidate.id}"]
        tracker = RunLlmTracker(max_calls=8)
        provider = ActivityProvider(ctx, tracker)
        provider.situation_output_active = True
        provider.situation_snapshot = enabled(db, SimpleNamespace(ctx=ctx, actor=seeded.world_character))
        state = {"identity": {"activity_id": ctx.run_id, "world_id": seeded.world.id,
            "actor_id": seeded.world_character.id}, "lane_data": {"prepared": freeze_prepared(prepared)} if prepared else {}}
        provider.situation_state = state
        payload = plain({"context": {"routine": build_routine_prompt_context(prepared.context, as_of_utc=now),
            "source_manifest": source_manifest(ctx, prepared)}}) if prepared else {}
        monkeypatch.setattr("app.runtime.autonomous_activity.provider._api_key", lambda _: "synthetic")
        yield SimpleNamespace(db=db, seeded=seeded, ctx=ctx, prepared=prepared, state=state,
            provider=provider, payload=payload, candidate=candidate, reply=reply, root=root, owner=owner, now=now)
    engine.dispose()


class JsonAdapter:
    capabilities = ProviderCapabilities(structured_json=True)

    def __init__(self, response=None):
        self.requests = []
        self.response = response or {"ok": True}

    async def generate_json(self, request):
        self.requests.append(request)
        value = self.response(request) if callable(self.response) else self.response
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, BaseException):
            raise value
        return ProviderResponse(json.dumps(value), value, ProviderUsage(), "STOP")

    def normalize_error(self, exc, *, api_key=None):
        from app.providers.contracts import ProviderError
        assert isinstance(exc, ProviderError), repr(exc)
        return exc


def install_adapter(monkeypatch, response=None):
    adapter = JsonAdapter(response)
    monkeypatch.setattr("app.integrations.direct_llm.get_provider_adapter", lambda *args: adapter)
    return adapter


async def submit(case):
    return await case.provider.call(node="RoutineDecisionDraft", lane="routine_decision_draft",
        system="Synthetic contract test.", payload=case.payload,
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        validator=lambda value: value, max_tokens=128)


def freeze(case):
    from app.runtime.autonomous_activity.situation_memory import freeze_social_input
    return freeze_social_input(case.ctx, case.provider.situation_snapshot,
        node="RoutineDecisionDraft", payload=case.payload,
        transmitted=json.dumps(case.payload, ensure_ascii=False), state=case.state)


def rebuild_input(case):
    case.state["lane_data"]["prepared"] = freeze_prepared(case.prepared)
    case.payload["context"]["routine"] = plain(build_routine_prompt_context(case.prepared.context, as_of_utc=case.now))
    case.payload["context"]["source_manifest"] = plain(source_manifest(case.ctx, case.prepared))


async def run_routine(case, monkeypatch, *, response=None):
    from app.runtime.autonomous_activity.combined_lanes import CombinedRoutineLane
    from app.runtime.autonomous_activity.graph import build_lane
    from app.runtime.autonomous_activity.inputs import shared_input
    from routine_posts.test_runtime import FakeRoutineProvider
    async def guard(_state):
        return {}
    lane = CombinedRoutineLane(case.ctx, actor=case.seeded.world_character,
        tracker=RunLlmTracker(max_calls=8), hybrid_service=None, guard=guard,
        ledger=SimpleNamespace(reserve=lambda _key: pytest.fail("valid output needs no repair")))
    lane.provider.situation_snapshot = case.provider.situation_snapshot
    case.lane = lane
    async def output(request):
        assert not case.db.in_transaction(), "no DB transaction during provider wait"
        generation = await FakeRoutineProvider().generate(resident_context=case.ctx,
            routine_context=lane.prepared.context, beat=lane.prepared.beat, tracker=RunLlmTracker(max_calls=2))
        return {"decision": {**generation.plan.model_dump(), "state_update": None, "state_source_refs": []},
            "draft": {**generation.draft.model_dump(), "thought": "I can try another measured step."},
            "situations": [{"target_id": "routine-post", "description": "A suggestion about the experiment informed the next scene."}]}
    adapter = install_adapter(monkeypatch, response or output)
    shared = shared_input(case.ctx, case.seeded.world_character, case.seeded.world)
    shared["now"] = case.now.isoformat()
    case.db.commit()
    state = await build_lane("routine", lane.ports(), combined=True).ainvoke({
        "identity": case.state["identity"], "shared_context": shared})
    return lane, state, adapter


def apply_situations(case):
    from datetime import UTC
    from app.domains.memory.service.scope import MemoryScopeService
    from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
    from app.domains.memory.repository.situation_apply import apply_page
    from app.domains.memory.models.activity_situation import MemorySituationApplyRun
    from app.runtime.memory.situation_application_sources import PreparedSituationSources
    from app.runtime.memory.composition import memory_repository
    db, scope, now = case.db, case.provider.situation_snapshot.scope, datetime.now(UTC)
    memory = memory_repository(db)
    setting = MemoryScopeService(memory).get_or_create(scope)
    get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=now)
    request = request_run(db, setting, trigger="manual", request_key="routine-source-apply", expected_version=1, now=now)
    token = claim_run(db, request.run_id, now=now)
    db.commit()
    for _ in range(5):
        if not token:
            break
        apply_page(db, memory, PreparedSituationSources(db), run_id=request.run_id, token=token, now=now)
        db.commit()
        if db.get(MemorySituationApplyRun, request.run_id).state == "completed":
            return
        token = claim_run(db, request.run_id, now=now)
        db.commit()
    assert db.get(MemorySituationApplyRun, request.run_id).state == "completed"
