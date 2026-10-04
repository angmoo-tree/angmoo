"""Canonical SQLite facts, rather than a new ranking, fence consumed SNS inputs."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from app.models import Base

from model_fixture_support import models
from social.test_feed_reaction_intent import _engine, _seed, _user, _character
from app.domains.relationships.contracts.graph_recall import GraphRecallScope, GraphRecallResult, GraphRecallStatus, GraphRecallSource
from app.domains.relationships.service.social_context import SocialContextService
from app.domains.relationships.policies.graph_recall import _relationship_record
from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
from app.runtime.autonomous_activity.social_lane import SocialLane
from app.domains.relationships.contracts.social_context import (
    CURRENTNESS_REVISION, CURRENTNESS_POLICY_KEY, LEGACY_CURRENTNESS,
    RelationshipValidationBinding, SocialContextValidationError,
)
from app.domains.relationships.policies.social_context_validation import receipt_for_snapshot

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.fixture
def relation_case(request, tmp_path):
    if getattr(request, "param", None) == "file":
        engine = create_engine("sqlite:///" + (tmp_path / "canonical.sqlite").as_posix())
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(engine)
    else:
        engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        ctx, _ = _seed(db, with_candidate=True)
        actor = db.get(models.WorldCharacter, "world-character-actor")
        owner = _user("peer")
        character = _character(owner, "peer")
        db.add_all([owner, character])
        db.flush()
        member = models.WorldMembership(id="member-peer", world_id=actor.world_id,
            user_id=owner.id, role="member", status="active")
        db.add(member)
        db.flush()
        peer = models.WorldCharacter(id="world-character-peer", world_id=actor.world_id,
            character_id=character.id, membership_id=member.id, role_key="student",
            status="active", autonomous_enabled=True, character_contract_hash="a" * 64,
            world_contract_hash="a" * 64)
        db.add(peer)
        db.flush()
        rows = []
        for target in ("world-character-author", peer.id):
            row = models.RelationshipState(id="rel-" + target, world_id=actor.world_id,
                actor_world_character_id=actor.id, target_world_character_id=target,
                familiarity=20, affinity=10, trust=12, tension=3, interaction_count=4,
                version=1, view_version=1, perception="A familiar peer",
                last_metric_at=datetime(2026, 10, 4, tzinfo=UTC))
            db.add(row)
            rows.append(row)
        db.commit()
        scope = GraphRecallScope(ctx.user_id, actor.world_id, actor.id)
        gateway = SqlAlchemyRelationshipGraphReadGateway(db)
        relations = [_relationship_record(gateway._relationship_hit(row)) for row in rows]
        labels = {"world-character-author": "Character author", peer.id: character.name}
        def snapshot(order):
            return SocialContextService(lambda query: GraphRecallResult(query.operation,
                GraphRecallStatus.READY, GraphRecallSource.GRAPH,
                relationships=tuple(order), candidate_count=len(order))).prepare(scope, labels=labels)
        yield SimpleNamespace(db=db, engine=engine, ctx=ctx, actor=actor, rows=rows, scope=scope,
            gateway=gateway, relations=relations, snapshot=snapshot)
    engine.dispose()


async def _scope_guard(_state):
    return {}


def _lane(case):
    lane = SocialLane.__new__(SocialLane)
    lane.ctx, lane.actor, lane.lane = case.ctx, case.actor, "feed"
    lane.scope_guard = _scope_guard
    lane.tracker = None
    lane.claim_validator = None
    return lane


def _state(case, snapshot):
    return {"identity": {"activity_id": case.ctx.run_id, "world_id": case.actor.world_id,
        "actor_id": case.actor.id}, "stage": "BuildDecisionContext",
        "candidates": [{"target_id": "post-target", "counterpart_id": "world-character-author",
            "relationship": snapshot.prompt_view(), "source_revisions": {}, "images": []}]}


@pytest.mark.parametrize("stage", ["BuildDecisionContext", "RecallSelected"])
@pytest.mark.parametrize("observed_role", ["Elias", "Red", "Bram"])
def test_t02_reordered_projection_does_not_invalidate_frozen_lane(relation_case, stage, observed_role):
    case = relation_case
    original, reordered = case.snapshot(case.relations), case.snapshot(list(reversed(case.relations)))
    assert original.content_hash != reordered.content_hash
    lane = _lane(case)
    lane.relationship = lambda _: reordered.prompt_view()
    state = {**_state(case, original), "stage": stage}
    asyncio.run(lane.guard(state))


def test_t04_changed_relationship_still_stops_lane(relation_case):
    case = relation_case
    original = case.snapshot(case.relations)
    case.rows[0].version += 1
    case.db.commit()
    lane = _lane(case)
    lane.relationship = lambda _: case.snapshot([replace(case.relations[0], relationship_version=2),
        case.relations[1]]).prompt_view()
    with pytest.raises(ValueError, match="activity_relationship_changed"):
        asyncio.run(lane.guard(_state(case, original)))


def test_t10_new_run_pins_policy_and_existing_legacy_run_is_not_rewritten(relation_case):
    from app.domains.world_characters.service.activity_engines import bind_run
    from app.domains.relationships.contracts.social_context import read_currentness_policy
    case = relation_case
    row = bind_run(case.db, actor=case.actor, activity_id="currentness-policy-run")
    assert row.result[CURRENTNESS_POLICY_KEY] == CURRENTNESS_REVISION
    case.db.commit()
    assert bind_run(case.db, actor=case.actor, activity_id=row.activity_id).result[CURRENTNESS_POLICY_KEY] == CURRENTNESS_REVISION
    # Represent a saved run created before this policy existed.
    row.result = {key: value for key, value in row.result.items() if key != CURRENTNESS_POLICY_KEY}
    case.db.commit()
    frozen = deepcopy(row.result)
    resumed = bind_run(case.db, actor=case.actor, activity_id=row.activity_id)
    assert resumed.result == frozen
    assert read_currentness_policy(resumed.result) == LEGACY_CURRENTNESS


def test_t25_multiple_candidates_share_one_guard_deadline(relation_case, monkeypatch):
    from time import monotonic
    from app.contracts.read_deadline import current_read_deadline
    from app.runtime.autonomous_activity import social_lane as owner
    case = relation_case
    lane, state = _lane(case), _new_state(case)
    second = deepcopy(state["candidates"][0])
    second["target_id"] = "second-target"
    state["candidates"].append(second)
    state["selections"] = []  # Selector guards every bounded candidate.
    receipt = deepcopy(state["relationship_validation_receipts"]["post-target"])
    receipt["binding"]["target_id"] = second["target_id"]
    state["relationship_validation_receipts"][second["target_id"]] = receipt
    original = owner.validate_relationship
    checked = []
    def validate(*args, **kwargs):
        assert current_read_deadline.get() is not None
        checked.append(kwargs["binding"].target_id)
        result = original(*args, **kwargs)
        # Move the clock boundary past the accumulated budget without sleep.
        current_read_deadline.set(monotonic() - 1)
        return result
    monkeypatch.setattr(owner, "validate_relationship", validate)
    with pytest.raises(SocialContextValidationError) as caught:
        asyncio.run(lane.guard(state))
    assert caught.value.reason == "canonical_unavailable"
    assert checked == ["post-target", "second-target"]
    assert current_read_deadline.get() is None


def _new_state(case, snapshot=None):
    snapshot = snapshot or case.snapshot(case.relations)
    state = _state(case, snapshot)
    state["identity"][CURRENTNESS_POLICY_KEY] = CURRENTNESS_REVISION
    binding = RelationshipValidationBinding(case.ctx.run_id, "feed", "post-target", "world-character-author")
    state["relationship_validation_receipts"] = {"post-target": receipt_for_snapshot(snapshot,
        scope=case.scope, binding=binding).to_dict()}
    state["selections"] = [{"target_id": "post-target"}]
    return state


def test_t06_projection_view_delay_uses_canonical_facts_in_original_rank(relation_case):
    from app.domains.relationships.service.graph_recall import GraphRecallService
    from test_p8_l_i_graph_recall import FakeGraphRepository
    case = relation_case
    graph = FakeGraphRepository()
    graph.ranked = [case.gateway._relationship_hit(row) for row in reversed(case.rows)]
    case.rows[1].view_version = 4
    case.rows[1].perception = "Canonical current perception"
    case.db.commit()
    service = GraphRecallService(case.gateway)
    snapshot = SocialContextService(lambda query: service.execute(query, repository=graph)).prepare(
        case.scope, labels={"world-character-author": "Character author", "world-character-peer": "Character peer"})
    assert snapshot.items[0].relationship.target_world_character_id == "world-character-peer"
    assert snapshot.items[0].relationship.view_version == 4
    assert "Canonical current perception" in snapshot.context_text
    state = _new_state(case, snapshot)
    before = deepcopy(state)
    asyncio.run(_lane(case).guard(state))
    graph.ranked.reverse()
    graph.ranked.insert(0, graph.ranked[-1])
    asyncio.run(_lane(case).guard(state))
    assert state == before


def test_t14_real_langgraph_checkpoint_preserves_hidden_receipts_and_input(tmp_path, relation_case):
    from langgraph.graph import StateGraph, START, END
    from app.runtime.autonomous_activity.contracts import LaneState
    from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, checkpoint_config
    from app.runtime.autonomous_activity.provider import candidate_previews
    from app.runtime.autonomous_activity.combined_selection import CombinedSelection
    import json
    case = relation_case
    state = _new_state(case)
    async def scenario():
        async with activity_checkpointer(tmp_path) as saver:
            builder = StateGraph(LaneState)
            builder.add_node("prepared", lambda s: {"relationship_validation_receipts": s["relationship_validation_receipts"]})
            builder.add_edge(START, "prepared"); builder.add_edge("prepared", END)
            graph = builder.compile(checkpointer=saver)
            config = checkpoint_config(activity_id=case.ctx.run_id)
            value = await graph.ainvoke(state, config)
            stored = await graph.aget_state(config)
            assert stored.values["relationship_validation_receipts"] == state["relationship_validation_receipts"]
            assert stored.values["identity"] == state["identity"]
            assert stored.values["candidates"][0]["relationship"] == state["candidates"][0]["relationship"]
            return value
    asyncio.run(scenario())
    candidate = {**state["candidates"][0], "source_ids": [], "allowed_actions": ["like"], "text": "A scene"}
    wire = json.dumps(candidate_previews([candidate], lane="feed"))
    assert "relationship_validation_receipts" not in wire and "facts_digest" not in wire
    selection = CombinedSelection({}, {})
    request = selection.request({"identity": state["identity"], "shared_context": {},
        "prepared_lanes": {"feed": {**state, "candidates": [candidate, {**candidate, "target_id": "other"}]}}})
    assert "relationship_validation_receipts" not in json.dumps(request)


def test_t15_inbox_change_refreshes_selected_prompt_and_receipt_together(relation_case, monkeypatch):
    from app.runtime.autonomous_activity.combined_lanes import CombinedFeedLane
    from app.runtime.autonomous_activity import inputs
    from app.integrations.direct_llm import RunLlmTracker
    from app.domains.world_characters.service.activity_engines import bind_run
    case = relation_case
    def current_snapshot(*_args, **_kwargs):
        rows = [_relationship_record(case.gateway._relationship_hit(row)) for row in case.rows]
        return case.snapshot(rows)
    monkeypatch.setattr(inputs, "relationship_snapshot", current_snapshot)
    lane = CombinedFeedLane(case.ctx, actor=case.actor, lane="feed", tracker=RunLlmTracker(max_calls=3),
        hybrid_service=None, guard=_scope_guard, ledger=SimpleNamespace(reserve=lambda _: None))
    run = bind_run(case.db, actor=case.actor, activity_id=case.ctx.run_id)
    case.db.commit()
    state = {"identity": {"activity_id": case.ctx.run_id, CURRENTNESS_POLICY_KEY: CURRENTNESS_REVISION}, "shared_context": {}}
    loaded = asyncio.run(lane.load(state))
    assert loaded["relationship_validation_receipts"]
    assert run.result["feed_preparation"]["relationship_validation_receipts"] == loaded["relationship_validation_receipts"]
    loaded = {**loaded, **state, "selections": [{"target_id": "post-target"}], "stage": "BuildDecisionContext"}
    previous = deepcopy(loaded)
    case.rows[0].version += 1; case.rows[0].affinity += 1; case.db.commit()
    refreshed = asyncio.run(lane.refresh_selected(loaded))
    assert loaded == previous
    assert refreshed["candidates"][0]["target_id"] == "post-target"
    assert refreshed["relationship_validation_receipts"]["post-target"] != previous["relationship_validation_receipts"]["post-target"]
    asyncio.run(lane.guard(refreshed))
    restored = __import__("json").loads(__import__("json").dumps(refreshed))
    asyncio.run(lane.guard(restored))
    case.rows[0].view_version += 1; case.db.commit()
    with pytest.raises(ValueError, match="activity_relationship_changed"):
        asyncio.run(lane.guard(restored))


@pytest.mark.parametrize("point", ["before_sdk", "json_retry"])
def test_t16_final_submission_guard_stops_real_provider_boundary(relation_case, monkeypatch, point):
    from app.integrations import direct_llm
    from app.providers.contracts import ProviderCapabilities, ProviderResponse, ProviderUsage
    from app.runtime.autonomous_activity import provider as transport
    from app.runtime.autonomous_activity.output_recovery import ActivityRetryGuardError
    case = relation_case
    lane, state = _lane(case), _new_state(case)
    calls = []
    class Adapter:
        capabilities = ProviderCapabilities(structured_json=True)
        async def generate_json(self, request):
            assert not case.db.in_transaction()
            calls.append(request)
            case.rows[0].version += 1; case.db.commit()
            return ProviderResponse('{"incomplete":', None, ProviderUsage(), "MAX_TOKENS")
    monkeypatch.setattr(direct_llm, "get_provider_adapter", lambda *_: Adapter())
    async def quota_wait(**_kwargs):
        if point == "before_sdk":
            case.rows[0].view_version += 1; case.db.commit()
    monkeypatch.setattr(direct_llm, "_RATE_LIMITER", SimpleNamespace(wait_if_needed=quota_wait))
    context = direct_llm.DirectLlmCallContext("fixture", case.actor.id, case.ctx.run_id,
        "FeedActionPlanner", "feed", "google", "gemini-3.1-flash-lite")
    monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic")
    monkeypatch.setattr(transport, "_llm_context", lambda *a, **kw: context)
    provider = transport.ActivityProvider(SimpleNamespace(db=case.db, generation_thinking_level=None, on_rate_limit_wait=None), direct_llm.RunLlmTracker(max_calls=3))
    async def guard(_attempt):
        try: await lane.guard(state)
        except Exception as exc: raise ActivityRetryGuardError(exc) from exc
    with pytest.raises(ActivityRetryGuardError):
        asyncio.run(provider.call(node="FeedActionPlanner", lane="feed", system="Plan", payload={},
            schema={"type": "object"}, validator=lambda x: x, max_tokens=20,
            recover_truncation=True, before_json_retry=guard, before_provider_request=guard))
    assert len(calls) == (0 if point == "before_sdk" else 1)
    assert all("facts_digest" not in request.user_prompt for request in calls)


@pytest.mark.parametrize("change", ["version", "block"])
def test_t17_inbox_executor_rejects_change_after_writer_and_commits_no_effect(relation_case, change):
    from sqlalchemy import select, func
    from app.runtime.social.planned_actions import _execute_planned_action
    case = relation_case
    lane, state = _lane(case), _new_state(case)
    lane.lane = "inbox"
    receipt = state["relationship_validation_receipts"]["post-target"]
    receipt["binding"]["lane"] = "inbox"
    if change == "version": case.rows[0].version += 1
    else: case.db.add(models.WorldCharacterBlock(id="writer-block", world_id=case.actor.world_id,
        blocker_world_character_id=case.actor.id, blocked_world_character_id="world-character-author"))
    case.db.commit()
    before = case.db.scalar(select(func.count(models.PostLike.id)))
    with pytest.raises(ValueError, match="activity_relationship_changed"):
        _execute_planned_action(case.ctx, action={"action_type": "like", "post_id": "post-target"},
            scope="inbox", index=0, writing={}, relationship_validator=lane.effect_relationship_validator(state, "post-target"))
    assert case.db.scalar(select(func.count(models.PostLike.id))) == before
    assert not case.db.scalar(select(models.AgentPublicActionExecution).where(models.AgentPublicActionExecution.status == "succeeded"))


def test_t18_completed_effect_replay_does_not_validate_changed_historical_facts(relation_case):
    case = relation_case
    lane, state = _lane(case), _new_state(case)
    lane.lane = "inbox"
    state["decision"] = {"decisions": [{"target_id": "post-target", "action": "like", "brief": "Acknowledge"}]}
    state["lane_data"] = {"post-target": {"post_id": "post-target"}}
    row = models.AgentPublicActionExecution(run_id=case.ctx.run_id, character_id=case.ctx.character.id,
        signature="complete-inbox", scope="inbox", action_type="like", target_post_id="post-target", status="succeeded")
    case.db.add(row); case.db.commit()
    case.rows[0].version += 1; case.db.commit()
    lane.action_executor = lambda *_a, **_kw: pytest.fail("committed action submitted again")
    state["stage"] = "Execute"
    asyncio.run(lane.guard(state))
    assert asyncio.run(lane.execute(state))["executions"][0]["status"] == "reused"


def test_t22_routine_uses_frozen_source_relations_but_solo_adds_no_reads(relation_case, monkeypatch):
    from app.runtime.autonomous_activity.routine import RoutineLane
    from app.domains.relationships.contracts.social_context import RelationshipValidationBinding
    case = relation_case
    lane = RoutineLane.__new__(RoutineLane)
    lane.ctx, lane.actor, lane.tracker = case.ctx, case.actor, None
    snapshot = case.snapshot(case.relations)
    counterpart = "world-character-author"
    state = {"identity": {"activity_id": case.ctx.run_id, CURRENTNESS_POLICY_KEY: CURRENTNESS_REVISION},
        "decision_context": {"relationships": {counterpart: snapshot.prompt_view()}},
        "relationship_validation_receipts": {counterpart: receipt_for_snapshot(snapshot, scope=case.scope,
            binding=RelationshipValidationBinding(case.ctx.run_id, "routine", counterpart, counterpart)).to_dict()}}
    lane.validate_relationships(state)
    case.rows[0].view_version += 1; case.db.commit()
    with pytest.raises(ValueError, match="routine_relationship_changed"):
        lane.validate_relationships(state)
    monkeypatch.setattr("app.runtime.autonomous_activity.routine.validate_relationship", lambda *a, **kw: pytest.fail("solo relation read"))
    lane.validate_relationships({"identity": state["identity"], "decision_context": {"relationships": {}}})


def test_t26_diagnostics_only_store_allowlisted_counts_and_reasons():
    # The observer adapter itself filters extra payloads and forged text codes.
    from app.runtime.diagnostics import sns_observation as diagnostics
    emitted = []
    recorder = SimpleNamespace(manifest={"schema_version": 3}, emit=lambda *a, **kw: emitted.append((a, kw)))
    diagnostics.SNSAttempt.tracker_event(recorder, "relationship_validation", {
        "lane": "feed", "revision": CURRENTNESS_REVISION, "outcome": "valid", "reason": None,
        "checked_count": 2, "receipt": "private persona and API key", "perception": "private"})
    assert emitted[0][1]["details"] == {"revision": CURRENTNESS_REVISION, "outcome": "valid", "reason": None, "checked_count": 2}
    diagnostics.SNSAttempt.tracker_event(recorder, "relationship_validation", {
        "lane": "feed", "revision": "private", "outcome": "private", "reason": "private", "checked_count": 10000})
    assert emitted[-1][1]["details"] == {"revision": None, "outcome": None, "reason": None, "checked_count": 12}


@pytest.mark.parametrize("relation_case", ["file"], indirect=True)
def test_t17_sqlite_writer_fence_blocks_changes_between_validation_and_publish(relation_case):
    from app.runtime.social.planned_actions import _execute_planned_action
    case = relation_case
    lane, state = _lane(case), _new_state(case)
    lane.lane = "inbox"
    state["relationship_validation_receipts"]["post-target"]["binding"]["lane"] = "inbox"
    checked = []
    validate = lane.effect_relationship_validator(state, "post-target")
    def fenced_validation():
        validate()
        with case.engine.connect() as other:
            other.exec_driver_sql("PRAGMA busy_timeout=1")
            with pytest.raises(OperationalError, match="locked"):
                other.exec_driver_sql("UPDATE relationship_states SET version=version+1 WHERE id=?", (case.rows[0].id,))
        checked.append(True)
    result = _execute_planned_action(case.ctx, action={"action_type": "like", "post_id": "post-target"},
        scope="inbox", index=0, writing={}, relationship_validator=fenced_validation)
    assert result["status"] == "succeeded"
    assert checked == [True]
    assert case.db.scalar(select(func.count(models.PostLike.id))) == 1


@pytest.mark.parametrize("change", ["version", "view", "claim", "source", "none"])
def test_t17_t18_feed_final_boundary_and_committed_reuse(relation_case, monkeypatch, change):
    from app.runtime.autonomous_activity.feed import FeedLane
    from app.runtime.autonomous_activity.planner_contract import parse_action
    from app.integrations.direct_llm import RunLlmTracker
    case = relation_case
    monkeypatch.setattr("app.runtime.autonomous_activity.inputs.relationship_snapshot", lambda *a, **kw: case.snapshot(case.relations))
    lane = FeedLane(case.ctx, actor=case.actor, lane="feed", tracker=RunLlmTracker(max_calls=2),
        hybrid_service=None, guard=_scope_guard)
    state = {"identity": {"activity_id": case.ctx.run_id, CURRENTNESS_POLICY_KEY: CURRENTNESS_REVISION}, "shared_context": {}}
    state.update(asyncio.run(lane.load(state)))
    assert state["candidates"][0]["target_id"] == "post-target"
    state["decision"] = parse_action({"decisions": [{"target_id": "post-target", "action": "like", "brief": "Recognize discovery"}]}, state["candidates"])
    if change == "version": case.rows[0].version += 1
    elif change == "view": case.rows[0].view_version += 1
    elif change == "claim": case.db.get(models.WorldCharacterFeedObservation, state["lane_data"]["_feed"]["observation_ids"][0]).claim_token = "changed"
    elif change == "source": case.db.get(models.Post, "post-target").body += " edited"
    case.db.commit()
    if change != "none":
        reason = "feed_claim_changed" if change == "claim" else "activity_source_changed" if change == "source" else "activity_relationship_changed"
        with pytest.raises(ValueError, match=reason):
            asyncio.run(lane.execute(state))
        assert case.db.scalar(select(func.count(models.PostLike.id))) == 0
        assert not case.db.scalar(select(models.AgentPublicActionExecution).where(models.AgentPublicActionExecution.status == "succeeded"))
    else:
        assert asyncio.run(lane.execute(state))["executions"][0]["status"] == "succeeded"
        case.rows[0].view_version += 1; case.db.commit()
        assert asyncio.run(lane.execute(state))["executions"][0]["status"] == "reused"
        assert case.db.scalar(select(func.count(models.PostLike.id))) == 1


@pytest.mark.parametrize("changed", [False, True])
def test_t17_t18_routine_publisher_respects_final_guard_and_reuses_effect(monkeypatch, changed):
    from routine_posts.test_runtime import _engine as routine_engine, _seed as routine_seed, _resident_context, _utc, FakeRoutineProvider
    from app.runtime.routine_posts.sqlalchemy_runtime import prepare_routine_activity, publish_routine_activity
    from app.runtime.autonomous_activity.inputs import ActivityRelationshipValidationError
    from app.integrations.direct_llm import RunLlmTracker
    from app.config import settings
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    engine = routine_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = routine_seed(db)
        ctx = _resident_context(db, fixture, run_id="canonical-routine-final", now=_utc(datetime(2026, 8, 10, 10, 5)))
        tracker = RunLlmTracker(max_calls=2)
        prepared = prepare_routine_activity(ctx, tracker=tracker, observe_inputs=False)
        generation = asyncio.run(FakeRoutineProvider().generate(resident_context=ctx,
            routine_context=prepared.context, beat=prepared.beat, tracker=tracker))
        before = db.scalar(select(func.count(models.Post.id)))
        calls = []
        def guard():
            calls.append(True)
            if changed:
                raise ActivityRelationshipValidationError("view_changed", lane="routine")
        if changed:
            with pytest.raises(ValueError, match="routine_relationship_changed"):
                publish_routine_activity(ctx, prepared=prepared, generation=generation, relationship_validator=guard)
            assert db.scalar(select(func.count(models.Post.id))) == before
        else:
            assert publish_routine_activity(ctx, prepared=prepared, generation=generation, relationship_validator=guard)["publish_result"]["public_action_count"] == 1
            def must_not_validate_again(): pytest.fail("completed Routine rechecked its old facts")
            assert publish_routine_activity(ctx, prepared=prepared, generation=generation,
                relationship_validator=must_not_validate_again)["routine_outcome"] == "REUSED_SUCCESS"
            assert db.scalar(select(func.count(models.Post.id))) == before + 1
        assert calls == [True]
    engine.dispose()
