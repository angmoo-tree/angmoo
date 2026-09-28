"""Behavioral coverage for the enum-preserving, energy-free Routine contract."""
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from copy import deepcopy
import asyncio

import pytest
from sqlalchemy import select, func, create_engine
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.config import settings
from app.domains.routine_posts import schemas
from app.contracts.routine_output import ENUM_OUTPUT, LEGACY_OUTPUT, RoutineOutputPolicy, saved_policy
from app.domains.routine_posts.service.evidence import build_routine_beat_plan_response_schema, freeze_request_context, _validate_plan
from app.domains.routine_posts.service.original_post import validate_original_post
from app.domains.routines.policies.activity_state import initial_state, apply_state_changes, project_state_v2, validate_state_snapshot
from app.domains.routines.models import AgentPublicActionExecution
from app.domains.routines.models.plans import ActivityBeat, ActivityEpisode
from app.domains.routines.service.execution.claims import claim_activity_beat, fail_activity_beat
from app.domains.routines.exceptions import ActivityRuntimeConflictError
from app.domains.social.models.posts import Post
from app.domains.world_characters.service.activity_engines import bind_run
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.combined_lanes import CombinedRoutineLane
from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from app.runtime.autonomous_activity.graph import build_lane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.routine_resume import freeze_prepared, restore_prepared
from app.runtime.routine_posts.original_post import completed_replies
from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc
from tests.routines.test_daily_preparation import preparation_scope, output as daily_output


@pytest.fixture(autouse=True)
def new_contract(monkeypatch):
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    monkeypatch.setattr(settings, "ROUTINE_OUTPUT_POLICY", "enum_preserved_v1")
    monkeypatch.setattr(settings, "ACTIVITY_THOUGHT_POLICY", "thought_v1")


@pytest.mark.parametrize("count", [0, 2, 4, 5, 7, 8])
def test_remaining_enums_and_bounds_are_identical(count):
    args = dict(has_previous_success=True, continuity_facts=["previous_post_id:post-a"],
        considered_source_event_ids=[f"event-{i}" for i in range(count)], detail_keys=["character.persona.description", "activity.title"])
    old = build_routine_beat_plan_response_schema(**args)
    new = build_routine_beat_plan_response_schema(**args, output_contract=ENUM_OUTPUT)
    for key in ("scene_kind", "continuity_facts", "used_source_event_ids", "used_detail_keys"):
        assert old["properties"][key] == new["properties"][key]
    for bound in ("minItems", "maxItems"):
        assert old["properties"]["source_event_effects"][bound] == new["properties"]["source_event_effects"][bound]
    assert old["properties"]["source_event_effects"]["items"]["properties"]["source_event_id"] == new["properties"]["source_event_effects"]["items"]["properties"]["source_event_id"]
    assert "episode_id" not in new["properties"] and "considered_source_event_ids" not in new["properties"]
    assert "motivation_kind" not in new["properties"]
    effect = new["properties"]["source_event_effects"]["items"]["properties"]
    assert set(effect) == {"source_event_id", "state_change"}
    assert set(effect["state_change"]["properties"]) == {"mood", "mood_intensity_delta", "action_note"}


@pytest.mark.parametrize("field", ["episode_id", "beat_id", "sequence_no", "considered_source_event_ids", "motivation_kind", "emotion_label"])
def test_wire_model_rejects_server_or_removed_fields(field):
    with pytest.raises(ValidationError):
        schemas.RoutineDecisionOutput.model_validate({"scene_kind": "start", "scene_brief": "scene", field: "invented"})


def test_energy_free_state_is_explicit_and_old_state_is_preserved():
    old = initial_state()
    original = deepcopy(old)
    new = project_state_v2(old, source_version=1)
    assert set(new) == {"mood", "mood_intensity", "action_note"}
    assert old == original
    assert initial_state(schema_version=2) == new
    assert apply_state_changes(new, [{"mood": "joyful", "mood_intensity_delta": 20}], schema_version=2)["mood_intensity"] == 20
    with pytest.raises(ValueError):
        apply_state_changes(new, [{"energy_delta": 0}], schema_version=2)
    with pytest.raises(ValueError):
        validate_state_snapshot(new, schema_version=1)
    assert validate_state_snapshot(old) == old


def test_policy_freezes_once_and_missing_run_never_upgrades(monkeypatch):
    with Session(_engine(), expire_on_commit=False) as db:
        fixture = _seed(db)
        run = bind_run(db, actor=fixture.world_character, activity_id="frozen-run")
        db.commit()
        assert saved_policy(run.result).output_contract == ENUM_OUTPUT
        monkeypatch.setattr(settings, "ROUTINE_OUTPUT_POLICY", "legacy")
        assert bind_run(db, actor=fixture.world_character, activity_id="frozen-run").result == run.result
        assert saved_policy(None).output_contract == LEGACY_OUTPUT
        assert saved_policy(bind_run(db, actor=fixture.world_character, activity_id="old-new-run").result).state_schema_version == 1


def _reply(db, fixture, ctx, *, succeeded=True, activity_id=None):
    root = Post(id="root", world_id=fixture.world.id, author_world_character_id=fixture.world_character.id,
        author_character_id=fixture.character.id, author_name="Synthetic", title="루트", body="루트 본문")
    reply = Post(id="reply", world_id=fixture.world.id, author_world_character_id=fixture.world_character.id,
        author_character_id=fixture.character.id, author_name="Synthetic", title="Re: 루트", body="상대에게 쓴 답글", reply_to_post_id="root", post_type="reply")
    db.add_all([root, reply])
    db.flush()
    receipt = AgentPublicActionExecution(run_id=activity_id or ctx.run_id, character_id=fixture.character.id,
        signature="synthetic-reply", scope="feed", action_type="reply", target_post_id=root.id,
        world_id=fixture.world.id, actor_world_character_id=fixture.world_character.id,
        status="succeeded" if succeeded else "failed", result={"post_id": reply.id})
    db.add(receipt)
    db.commit()
    return reply


@pytest.mark.parametrize("mode", ["combined", "split"])
@pytest.mark.parametrize("duplicate", ["none", "repair", "twice"])
def test_new_runtime_one_call_repair_bound_and_canonical_reuse(monkeypatch, mode, duplicate):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            fixture = _seed(db)
            ctx = _resident_context(db, fixture, run_id="new-contract-run", now=_utc(datetime(2026, 8, 10, 10, 5)))
            run = bind_run(db, actor=fixture.world_character, activity_id=ctx.run_id)
            db.commit()
            reply = _reply(db, fixture, ctx) if duplicate != "none" else None
            shared = shared_input(ctx, fixture.world_character, fixture.world)
            shared["now"] = ctx.run_started_at.isoformat()
            if mode == "split":
                shared["synthetic_large_context"] = "합성 맥락 " * 8000
            calls = []
            async def guard(state):
                return {}
            lane = CombinedRoutineLane(ctx, actor=fixture.world_character, tracker=RunLlmTracker(max_calls=8), hybrid_service=None,
                guard=guard, ledger=RecoveryLedger(db, ctx.run_id))
            async def call(_provider, **kwargs):
                calls.append(kwargs["node"])
                assert "NEW root SNS post" in kwargs["system"]
                bad = duplicate == "twice" or (duplicate == "repair" and len(calls) == (1 if mode == "combined" else 2))
                draft = {"title": reply.title if bad else "오전 기록", "body": reply.body if bad else "오전 훈련 중 균형을 연습했다.", "novelty_basis": "현재 장면", "thought": "균형을 지키고 싶었다."}
                if kwargs["node"] in {"RoutineActionPlanner", "RoutineDecisionDraft"}:
                    frozen = freeze_prepared(lane.prepared)
                    lane.prepared = restore_prepared(ctx, frozen, lane.tracker)
                    schema = kwargs["schema"]["properties"]["decision"] if mode == "combined" else kwargs["schema"]
                    assert "episode_id" not in schema["properties"]
                    assert "energy" not in kwargs["payload"]["routine"]["state_before"]
                    decision = {"scene_kind": "start", "scene_brief": "오전 실습의 균형을 연습한다.", "continuity_facts": [],
                        "used_source_event_ids": [], "used_detail_keys": ["activity.title"], "source_event_effects": [], "state_update": None,
                        "state_source_refs": [], "relationship_metrics": None}
                    return kwargs["validator"]({"decision": decision, "draft": draft} if mode == "combined" else decision)
                if len(calls) > (1 if mode == "combined" else 2):
                    assert kwargs["payload"]["writer_feedback"]["validation_code"] == "routine_reuses_published_reply"
                return kwargs["validator"](draft)
            monkeypatch.setattr(ActivityProvider, "call", call)
            state = {"identity": {"activity_id": ctx.run_id}, "shared_context": shared, "generation_mode": mode}
            result = await build_lane("routine", lane.ports(), combined=True).ainvoke(state)
            expected = 1 if mode == "combined" else 2
            assert len(calls) == expected + (duplicate != "none")
            db.refresh(run)
            assert len((run.result or {}).get("recovery_reservations", [])) == (duplicate != "none")
            if duplicate == "twice":
                assert result["failure"]["reason"] == "routine_reuses_published_reply"
                assert result["result"]["public_action_count"] == 0
                assert db.get(Post, "reply") is not None
                return
            assert result["result"]["public_action_count"] == 1
            beat = db.scalar(select(ActivityBeat).where(ActivityBeat.status == "succeeded"))
            assert beat.state_schema_version == 2
            assert "energy" not in beat.state_after_snapshot
            assert beat.result_snapshot["routine_output_contract"] == ENUM_OUTPUT
            # The final new-contract post and thought remain usable by the
            # current memory source path, rather than legacy declarations.
            from app.domains.memory.contracts.scope import MemoryScope
            from app.runtime.memory.episode_social_sources import build_episode_social_sources
            from app.domains.routines.schemas.plans import ActivityEpisodeRead
            source = build_episode_social_sources(db, scope=MemoryScope(fixture.user.id,
                fixture.world.id, fixture.world_character.id), identities=(("POST", beat.source_post_id),))
            assert len(source.inputs) == 1 and source.rejected == ()
            unit = source.inputs[0].unit
            assert unit.thought_reference.startswith("social:")
            assert any("오전 훈련 중 균형" in member.text for member in unit.members)
            episode_view = ActivityEpisodeRead.model_validate(db.get(ActivityEpisode, beat.episode_id))
            assert episode_view.current_state_schema_version == 2
            assert "energy" not in episode_view.current_state_snapshot
            # Disabling new starts must not reinterpret the already-published
            # contract or recreate legacy energy values during a replay.
            monkeypatch.setattr(settings, "ROUTINE_OUTPUT_POLICY", "legacy")
            lane.prepared = restore_prepared(ctx, freeze_prepared(lane.prepared), lane.tracker)
            replay = await lane.execute(result)
            assert replay["executions"][0]["routine_outcome"] == "REUSED_SUCCESS"
            assert len(calls) == expected + (duplicate != "none")
    asyncio.run(scenario())


def test_copy_rule_checks_both_title_and_body_without_re_ban():
    replies = [{"title": "Re: hello", "body": "one\r\ntwo"}]
    with pytest.raises(ValueError, match="routine_reuses_published_reply"):
        validate_original_post(title=" Re: hello ", body="one\ntwo", completed_replies=replies)
    validate_original_post(title="Re: new scene", body="one\ntwo", completed_replies=replies)
    validate_original_post(title="Re: hello", body="new", completed_replies=replies)


def test_receipt_scope_failure_and_recent_list_do_not_control_copy_guard():
    with Session(_engine(), expire_on_commit=False) as db:
        fixture = _seed(db)
        ctx = _resident_context(db, fixture, run_id="scope-run", now=_utc(datetime(2026, 8, 10, 10, 5)))
        _reply(db, fixture, ctx, succeeded=False)
        assert completed_replies(ctx, world_id=fixture.world.id, actor_id=fixture.world_character.id) == []
        receipt = db.scalar(select(AgentPublicActionExecution))
        receipt.status = "succeeded"
        db.commit()
        assert completed_replies(ctx, world_id="other-world", actor_id=fixture.world_character.id) == []
        assert completed_replies(ctx, world_id=fixture.world.id, actor_id="other-actor") == []
        assert len(completed_replies(ctx, world_id=fixture.world.id, actor_id=fixture.world_character.id)) == 1


def test_sqlite_version_migration_keeps_old_snapshot_bytes():
    from app.runtime.migrations.sqlite_versions import routine_state_v24
    with create_engine("sqlite://").begin() as connection:
        connection.exec_driver_sql("CREATE TABLE activity_beats (id TEXT PRIMARY KEY, state_before_snapshot TEXT NOT NULL, result_snapshot TEXT)")
        connection.exec_driver_sql("INSERT INTO activity_beats VALUES ('old', '{\"energy\":50}', '{\"emotion_text\":\"old\"}')")
        before = routine_state_v24.capture_delta(connection)
        routine_state_v24.upgrade(connection)
        routine_state_v24.verify_delta(connection, before)
        assert connection.exec_driver_sql("SELECT state_schema_version, state_before_snapshot FROM activity_beats").one() == (1, '{"energy":50}')


def _claim(db, episode, now, *, version, key, run):
    return claim_activity_beat(db, episode_id=episode.id, scheduled_for=now, trigger_kind="scheduled",
        idempotency_key=key, claim_run_id=run, claim_expires_at=now + timedelta(minutes=10),
        state_schema_version=version, now=now).row


def test_inflight_old_beat_blocks_transition_and_history_survives():
    with Session(_engine(), expire_on_commit=False) as db:
        fixture = _seed(db)
        now = _utc(datetime(2026, 8, 10, 10, 0))
        old = _claim(db, fixture.morning_episode, now, version=1, key="old", run="old-run")
        snapshot = deepcopy(old.state_before_snapshot)
        with pytest.raises(ActivityRuntimeConflictError, match="activity_state_transition_pending"):
            _claim(db, fixture.morning_episode, now + timedelta(minutes=30), version=2, key="new", run="new-run")
        db.rollback()
        assert fixture.morning_episode.current_state_schema_version == 1
        fail_activity_beat(db, beat_id=old.id, claim_run_id="old-run", reason_code="synthetic_failure", now=now)
        new = _claim(db, fixture.morning_episode, now + timedelta(minutes=30), version=2, key="new", run="new-run")
        assert new.state_schema_version == fixture.morning_episode.current_state_schema_version == 2
        assert set(new.state_before_snapshot) == {"mood", "mood_intensity", "action_note"}
        db.refresh(old)
        assert old.state_schema_version == 1 and old.state_before_snapshot == snapshot


def test_file_sqlite_competing_transition_only_claims_once(tmp_path):
    from app.models import Base
    engine = create_engine(f"sqlite:///{tmp_path / 'claims.sqlite'}", connect_args={"timeout": 30})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        episode_id = _seed(db).morning_episode.id
    barrier = Barrier(2)
    now = _utc(datetime(2026, 8, 10, 10, 0))
    def compete(index):
        with Session(engine) as db:
            episode = db.get(ActivityEpisode, episode_id)
            barrier.wait(timeout=10)
            try:
                _claim(db, episode, now, version=2, key="same-tick", run=f"claim-{index}")
                return "claimed"
            except ActivityRuntimeConflictError:
                db.rollback()
                return "conflict"
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(compete, (0, 1)))
    assert sorted(outcomes) == ["claimed", "conflict"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ActivityBeat)) == 1
        assert db.get(ActivityEpisode, episode_id).current_state_schema_version == 2
    engine.dispose()


def test_server_binding_rejects_changed_input_before_applying_decision():
    from app.runtime.routine_posts.sqlalchemy_runtime import prepare_routine_activity
    from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput
    from app.domains.routine_posts.service.evidence import bind_decision
    with Session(_engine(), expire_on_commit=False) as db:
        fixture = _seed(db)
        ctx = _resident_context(db, fixture, run_id="binding-run", now=_utc(datetime(2026, 8, 10, 10, 5)))
        prepared = prepare_routine_activity(ctx, output_policy=RoutineOutputPolicy(ENUM_OUTPUT, 2, "thought_v1"))
        event = RoutineInteractionInput("event-a", fixture.world.id, fixture.world_character.id,
            "other", "정정된 사실", ctx.run_started_at)
        context = replace(prepared.context, source_events=(event,))
        frozen = freeze_request_context(context, prepared.beat)
        wire = {"scene_kind": "start", "scene_brief": "현재 장면", "used_source_event_ids": ["event-a"]}
        bound = bind_decision(wire, request=frozen, context=context, beat=prepared.beat)
        assert bound.considered_source_event_ids == bound.used_source_event_ids == ["event-a"]
        with pytest.raises(ValidationError):
            _validate_plan(bound.model_dump(), context=context, beat=prepared.beat, request=frozen)
        for changed in (replace(context, source_events=(replace(event, excerpt="수정된 원문"),)),
                        replace(context, state_before={**context.state_before, "action_note": "바뀐 상태"})):
            with pytest.raises(ValueError, match="routine_request_context_changed"):
                bind_decision(wire, request=frozen, context=changed, beat=prepared.beat)


def test_copy_guard_queries_all_successes_instead_of_recent_twelve():
    from app.runtime.routine_posts.original_post import check_original
    with Session(_engine(), expire_on_commit=False) as db:
        fixture = _seed(db)
        ctx = _resident_context(db, fixture, run_id="many-replies", now=_utc(datetime(2026, 8, 10, 10, 5)))
        oldest = _reply(db, fixture, ctx)
        for index in range(13):
            post = Post(id=f"reply-{index}", world_id=fixture.world.id,
                author_world_character_id=fixture.world_character.id, author_character_id=fixture.character.id,
                author_name="Synthetic", title=f"새 답글 {index}", body=f"새 내용 {index}",
                reply_to_post_id="root", post_type="reply")
            db.add(post)
            db.flush()
            db.add(AgentPublicActionExecution(run_id=ctx.run_id, character_id=fixture.character.id,
                signature=f"many-{index}", scope="inbox", action_type="reply", target_post_id="root",
                world_id=fixture.world.id, actor_world_character_id=fixture.world_character.id,
                status="succeeded", result={"post_id": post.id}))
        db.commit()
        assert len(completed_replies(ctx, world_id=fixture.world.id, actor_id=fixture.world_character.id)) == 14
        with pytest.raises(ValueError, match="routine_reuses_published_reply"):
            check_original(ctx, world_id=fixture.world.id, actor_id=fixture.world_character.id,
                title=oldest.title, body=oldest.body)


def test_completed_reply_prompt_references_existing_text_without_losing_omitted_reply():
    from app.runtime.routine_posts.original_post import reply_prompt_context
    replies = [{"post_id": "present", "title": "제목", "body": "이미 쓴 답글", "purpose": "already_published_reply"},
               {"post_id": "omitted", "title": "오래된 제목", "body": "입력 목록 밖 답글", "purpose": "already_published_reply"}]
    today = {"records": [{"record_key": "post:present", "source_post_id": "present", "title": "제목", "body": "이미 쓴 답글"}]}
    result = reply_prompt_context(replies, today)
    assert result[0]["content_ref"] == "today_activity.records:post:present"
    assert "body" not in result[0] and "title" not in result[0]
    assert result[1] == replies[1]
    assert replies[0]["body"] == "이미 쓴 답글" and today["records"][0]["body"] == "이미 쓴 답글"


def test_daily_runtime_and_repertoire_factory_select_energy_free_state(preparation_scope, monkeypatch):
    from app.domains.routines.schemas.daily_generation import InitialPreparationOutput
    from tests.routines.test_daily_activity_runtime import _engine as plan_engine, _seed as plan_seed, _prepare
    db, world, ready, runtime = preparation_scope
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs["initial"])
        kwargs["reserve"]()
        return InitialPreparationOutput(daily_plan=daily_output(), recommendation_topics=[dict(name="기록", scope="common")]), SimpleNamespace(calls=[])
    status = asyncio.run(runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
        user=ready.user, request_id="new-state-plan", now=datetime.now(UTC), generator=generate))
    assert status.plan_state == "ready" and calls == [True], status
    db.expire_all()
    episodes = list(db.scalars(select(ActivityEpisode)))
    assert episodes and all(e.current_state_schema_version == 2 for e in episodes)
    assert all(set(e.current_state_snapshot) == {"mood", "mood_intensity", "action_note"} for e in episodes)

    # Compatibility candidate preparation can also create a new-policy plan;
    # legacy regression modules opting out must not change this real factory.
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    engine = plan_engine()
    with Session(engine, expire_on_commit=False) as plan_db:
        _, fixture, _ = plan_seed(plan_db)
        plan = _prepare(plan_db, fixture, now=_utc(datetime(2026, 8, 10, 10)))
        states = [item.episode for item in plan.items if item.episode is not None]
        assert states and all(e.current_state_schema_version == 2 for e in states)
        assert all("energy" not in e.current_state_snapshot for e in states)
    engine.dispose()


def test_routine_diagnostic_codes_and_provenance_do_not_expose_generated_text():
    from app.runtime.diagnostics.sns_observation import _node_summary, _safe_error, validation_code
    duplicate = "routine_reuses_published_reply"
    assert validation_code(duplicate) == duplicate
    assert validation_code("raw private content") is None
    assert _safe_error(ValueError(duplicate))["error_code"] == duplicate
    result = {"decision": {"routine_request": {"output_contract": ENUM_OUTPUT, "state_schema_version": 2},
        "plan": {"considered_source_event_ids": ["event-a", "event-b"], "used_source_event_ids": ["event-b"],
                 "scene_brief": "private scene text"}}}
    summary = _node_summary("DecisionDraft", {}, result)
    assert summary["routine_output_contract"] == ENUM_OUTPUT and summary["routine_state_schema_version"] == 2
    assert summary["routine_considered_ids"] == ["event-a", "event-b"] and summary["routine_used_ids"] == ["event-b"]
    assert "private scene text" not in str(summary)
