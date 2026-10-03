"""V2 selection/generation/public effects to ordinary daily materialization.

Only provider transport and the authenticated publishing port are fakes. Proposal,
notification, execution, reservation and two-plan persistence are the real owners.
"""
import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.models import Base
from app.integrations.direct_llm import RunLlmTracker
from app.domains.routines.contracts.plans import PlanScope
from app.domains.identity.service.environment import snapshot as environment_snapshot
from app.domains.routines.service import daily_preparation as store
from app.domains.routines.service import plans
from app.domains.social.schemas.feed import WorldFeedCandidateRead
from app.domains.social.schemas.feed import JointActivityProposalPreview
from app.domains.social.service.recommendation_topics import mark_new_subject
from app.runtime import daily_preparation as preparation
from app.runtime.activity_proposals import composition as proposals
from app.runtime.autonomous_activity import provider as transport
from app.runtime.autonomous_activity.combined_lanes import CombinedFeedLane, CombinedInboxLane
from app.runtime.autonomous_activity.combined_selection import CombinedSelection
from app.runtime.autonomous_activity.contracts import Candidate
from app.runtime.social.planned_actions import _execute_planned_action
from app.runtime.routines.plan_references import SqlAlchemyPlanReferences
from app.runtime.social.agent_tools import agent_tool_actions
from model_fixture_support import models
from tests.characters.name_binding_fixture import create_profile
from tests.relationships.test_activity_proposals import _post, _record_post_event
from tests.routines.test_daily_activity_runtime import _seed, _utc
from tests.routines.test_daily_preparation import output
from tests.routines.test_ordinary_daily_generation import new_output, topics_ready


def database(path):
    engine = create_engine(f"sqlite:///{path}")
    event.listen(engine, "connect", lambda raw, _: raw.execute("PRAGMA foreign_keys=ON"))
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(engine)
    return engine


def pair(db):
    world, first, original_second = _seed(db, two_characters=True)
    # The original fixture has an explicit Seoul user calendar. Direct planning
    # calls below must freeze that same environment instead of defaulting to UTC.
    assert environment_snapshot(db, first.user.id).timezone == "Asia/Seoul"
    first = SimpleNamespace(character=first.character, world_character=first.world_character,
        user=first.user, membership=first.membership,
        credential=db.scalar(select(models.LlmCredential).where(models.LlmCredential.character_id == first.character.id)))
    second_credential = db.scalar(select(models.LlmCredential).where(models.LlmCredential.character_id == original_second.character.id))
    original_second.character.owner_id = first.user.id
    second_credential.owner_id = first.user.id
    original_second.world_character.membership_id = first.membership.id
    second = SimpleNamespace(character=original_second.character, world_character=original_second.world_character,
        user=first.user, membership=first.membership, credential=second_credential)
    create_profile(db, world, first.user.id, "Alex")
    db.add(models.WorldRole(id="joint-test-role", world_id=world.id, role_key="student", name="주민"))
    for ready in (first, second):
        ready.world_character.autonomous_enabled = True
        ready.world_character.feed_runtime_mode = "topic_recommendation_v1"
        ready.world_character.activity_runtime_mode = "routine_resident_v1"
        mark_new_subject(db, world_id=world.id, world_character_id=ready.world_character.id)
        topics_ready(db, world, ready)
        db.add(models.CharacterActiveWorld(character_id=ready.character.id,
            world_character_id=ready.world_character.id, selected_at=datetime.now(UTC),
            idempotency_key=ready.character.id, version=1))
    db.commit()
    return world, first, second


def save_plan(db, world, ready, target, now):
    return store.apply_plan(db, scope=PlanScope(world, ready.membership, ready.world_character, ready.character,
        environment_snapshot(db, ready.user.id)),
        output=output(), target_date=target, now=now, source_digest="a" * 64, expected_snapshot={})


def context(db, ready, lane):
    identifier = f"v2-{ready.character.id}-{lane}"
    db.add(models.AgentRun(id=identifier, user_id=ready.user.id, character_id=ready.character.id,
        agent_id=identifier, session_key=identifier, credential_id=ready.credential.id, status="running"))
    db.commit()
    return SimpleNamespace(db=db, run_id=identifier, user_id=ready.user.id, character=ready.character,
        credential=ready.credential, generation_model="test", generation_thinking_level="high",
        on_rate_limit_wait=None, session_key=identifier, social_context=None,
        activity_policy=SimpleNamespace(allowed_actions={"post", "reply", "like"}))


def adapter(cls, ctx, ready, lane):
    async def guard(_):
        return {}
    value = cls(ctx, actor=ready.world_character, lane=lane, tracker=RunLlmTracker(),
        hybrid_service=None, guard=guard, ledger=SimpleNamespace(reserve=lambda _: None),
        action_executor=_execute_planned_action)
    return value


async def generate_and_write(lane, state):
    state.update(await lane.context(state))
    state.update(await lane.plan(state))
    state.update(await lane.validate(state))
    state.update(await lane.write(state))
    return state


@pytest.mark.parametrize("existing,next_date", [(0, False), (1, False), (2, False), (0, True)])
def test_v2_original_proposal_acceptance_and_both_daily_plans(tmp_path, monkeypatch, existing, next_date):
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", True)
    engine = database(tmp_path / "joint-flow.sqlite3")
    requests = []
    with Session(engine, expire_on_commit=False) as db:
        world, first, second = pair(db)
        now = datetime.now(UTC)
        target = now.astimezone(ZoneInfo(world.timezone)).date() + timedelta(days=2 if next_date else 1)
        for ready in (first, second)[:existing]:
            save_plan(db, world, ready, target, now)
        root = _post(db, post_id="joint-flow-root", fixture=second,
            body="내일은 정원에서 쉬고 싶어.", created_at=now)
        _record_post_event(db, world_id=world.id, actor_world_character_id=second.world_character.id,
            target_world_character_id=None, event_type="post_published", source=root,
            target_post_id=None, root_post_id=root.id, occurred_at=now, idempotency_key="root-event")
        db.commit()

        def publish(session, session_key, post_id, data):
            ready = first if data.author_character_id == first.character.id else second
            other = second if ready is first else first
            post = _post(session, post_id=f"public-{session_key}", fixture=ready, body=data.body,
                created_at=datetime.now(UTC), reply_to_post_id=post_id)
            session.add(models.Notification(world_id=world.id, recipient_character_id=other.character.id,
                recipient_world_character_id=other.world_character.id, actor_character_id=ready.character.id,
                actor_world_character_id=ready.world_character.id, notification_type="reply",
                post_id=post_id, source_post_id=post.id))
            session.flush()
            return post
        monkeypatch.setattr(agent_tool_actions, "reply_agent_tool_post", publish)
        monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic")
        monkeypatch.setattr(transport, "_llm_context", lambda _, **kw: SimpleNamespace(node=kw["node"]))

        async def provider(**kw):
            requests.append(kw["context"].node)
            payload = json.loads(kw["user_prompt"])
            candidates = payload.get("candidates", payload.get("selected_targets", []))
            if "Selector" in kw["context"].node:
                chosen = next(row for row in candidates if row.get("activity_proposal"))
                return kw["validator"]({"selections": [{"target_id": chosen["target_id"], "memory_query": None}]})
            chosen = candidates[0]
            if kw["context"].node == "FeedDecisionDraft":
                action = dict(target_id=root.id, action="comment", interaction_intent="joint_activity_proposal",
                    brief="미래 저녁 정원에서 함께 쉬자고 제안", proposal=dict(source_post_id=root.id,
                        target_world_character_id=second.world_character.id, activity_seed="정원에서 함께 쉬기",
                        target_daypart="evening", date_policy="exact", target_date=str(target)))
                reply = dict(target_id=root.id, body="그날 저녁에 함께 정원에서 쉴래?")
            else:
                action = dict(target_id=chosen["target_id"], action="comment", interaction_intent="proposal_response",
                    brief="제안된 저녁 정원 휴식 승낙", proposal_response={"proposal_decision": "accept"})
                reply = dict(target_id=chosen["target_id"], body="좋아, 그날 저녁에 정원에서 만나자.", proposal_decision="accept")
            return kw["validator"]({"decision": {"decisions": [action], "state_update": None,
                "relationship_metrics": []}, "draft": {"replies": [reply]}})
        monkeypatch.setattr(transport, "generate_json", provider)
        feed_ctx = context(db, first, "feed")
        feed = adapter(CombinedFeedLane, feed_ctx, first, "feed")
        observation = models.WorldCharacterFeedObservation(id="feed-observation", world_id=world.id,
            observer_world_character_id=first.world_character.id, post_id=root.id, status="claimed",
            claim_token="token", lease_expires_at=now+timedelta(hours=1), cycle_key="joint-cycle", run_id=feed_ctx.run_id,
            post_created_at=now, claimed_at=now)
        db.add(observation); db.commit()
        raw = WorldFeedCandidateRead(candidate_index=0, post_id=root.id, author_world_character_id=second.world_character.id,
            author_character_id=second.character.id, author_name=second.character.name, title=root.title, body_preview=root.body,
            topic_signature="정원", created_at=now, world_local_datetime=now.isoformat(), age_seconds=0, age_bucket="recent",
            matched_keywords=["정원"], matched_fields=["body"], rank_score=1, allowed_actions=["comment"])
        from app.runtime.relationships.experience_metrics import post_revision
        candidate = Candidate(target_id=root.id, counterpart_id=second.world_character.id, source_ids=[root.id],
            source_revisions={root.id: post_revision(root)}, text=root.body, allowed_actions=["comment"],
            proposal_eligible=True, relationship=feed.relationship(second.world_character.id)).model_dump()
        base = dict(identity={"activity_id": feed_ctx.run_id, "contract_version": 2}, shared_context={"current_state": {"version": 0}},
            memories={}, memory_validations={}, generation_mode="combined")
        feed_state = {**base, "candidates": [candidate], "lane_data": {root.id: {"post_id": root.id}, "_feed": {
            "candidates": [raw.model_dump(mode="json")], "cycle_key": "joint-cycle", "observation_ids": [observation.id],
            "claim_tokens": {observation.id: observation.claim_token}}}, "selections": [{"target_id": root.id}]}
        selector = CombinedSelection({"inbox": feed, "feed": feed}, {"inbox": feed.ports(), "feed": feed.ports()})
        selection = asyncio.run(selector.select({**base, "selection_mode": "combined",
            "prepared_lanes": {"inbox": {"candidates": []}, "feed": feed_state}}))
        feed_state.update(selection["prepared_lanes"]["feed"])
        asyncio.run(generate_and_write(feed, feed_state))
        feed_execution = asyncio.run(feed.execute(feed_state))["executions"][0]
        assert feed_execution["status"] == "succeeded"
        proposal = db.scalar(select(models.ActivityProposal))
        original = db.get(models.Post, db.get(models.AgentPublicActionExecution, feed_execution["execution_id"]).result["post_id"])
        assert proposal.status == "proposed" and db.scalar(select(func.count(models.JointActivity.id))) == 0
        later = _post(db, post_id="joint-flow-later", fixture=first, body="사진도 예쁘다.",
            created_at=datetime.now(UTC), reply_to_post_id=root.id)
        db.add(models.Notification(world_id=world.id, recipient_character_id=second.character.id,
            recipient_world_character_id=second.world_character.id, actor_character_id=first.character.id,
            actor_world_character_id=first.world_character.id, notification_type="reply", post_id=root.id, source_post_id=later.id))
        db.commit()
        inbox = adapter(CombinedInboxLane, context(db, second, "inbox"), second, "inbox")
        state = {**base, "identity": {"activity_id": inbox.ctx.run_id, "contract_version": 2}, **asyncio.run(inbox.load(base))}
        selector = CombinedSelection({"inbox": inbox, "feed": feed}, {"inbox": inbox.ports(), "feed": feed.ports()})
        selection = asyncio.run(selector.select({**base, "selection_mode": "combined",
            "prepared_lanes": {"inbox": state, "feed": {"candidates": []}}}))
        state.update(selection["prepared_lanes"]["inbox"])
        asyncio.run(generate_and_write(inbox, state))
        assert state["assignments"][0]["target_post_id"] == original.id
        assert state["drafts"][0]["proposal_response"]["proposal_id"] == proposal.id
        state.update(asyncio.run(inbox.execute(state)))
        assert state["executions"][0]["status"] == "succeeded", state["executions"]
        asyncio.run(inbox.finalize(state))
        joint = db.scalar(select(models.JointActivity))
        assert joint.source_acceptance_event_id and proposal.status == "accepted"
        participants = list(db.scalars(select(models.JointActivityParticipant)))
        assert len(participants) == 2
        # One missing plan keeps both reservations unmaterialized until the
        # second plan is created; no one-sided schedule is published.
        assert sum(row.linked_daily_activity_plan_item_id is not None for row in participants) == (2 if existing == 2 else 0)
        assert db.scalar(select(models.Notification).where(models.Notification.source_post_id == later.id)).handled_at is None
        assert db.scalar(select(models.SocialEvent).where(models.SocialEvent.id == joint.source_acceptance_event_id)).event_type == "joint_accepted"
        # Same checkpoint after public commit must reuse the execution, not reply again.
        asyncio.run(inbox.guard({**state, "stage": "Execute"}))
        assert asyncio.run(inbox.execute(state))["executions"][0]["status"] == "reused"
        assert db.scalar(select(func.count(models.JointActivity.id))) == 1
        for ready in (first, second)[existing:]:
            scope = PlanScope(world, ready.membership, ready.world_character, ready.character,
                environment_snapshot(db, ready.user.id))
            local_now = _utc(datetime.combine(target, datetime.min.time()) + timedelta(hours=7))
            source, _, _, allowed = preparation._source(db, scope, local_now)
            assert "evening" not in source["generated_dayparts"]
            ordinary = new_output(source).daily_plan
            full = store.compose_generated_plan(ordinary, generated_dayparts=source["generated_dayparts"],
                fixed_items=source["fixed_items"], allowed_places=allowed)
            store.apply_plan(db, scope=scope, output=full, target_date=target, now=local_now,
                source_digest="b" * 64, expected_snapshot={})
            db.commit()
        db.expire_all()
        assert db.get(models.JointActivity, joint.id).status == "ready"
        assert all(row.linked_daily_activity_plan_item_id and row.linked_activity_episode_id
            for row in db.scalars(select(models.JointActivityParticipant)))
        for ready in (first, second):
            plan = store.current_plan(db, ready.world_character.id, target)
            rows = store.current_items(db, plan.id)
            assert len(rows) == 4
            assert sum(row.joint_activity_id == joint.id for row in rows) == 1
            api_plan = plans.get_activity_plan(db, character_id=ready.character.id, world_id=world.id,
                user=ready.user, references=SqlAlchemyPlanReferences(db),
                now=_utc(datetime.combine(target, datetime.min.time())+timedelta(hours=7)))
            assert len(api_plan.items) == 4
            assert sum(item.joint_activity_id == joint.id for item in api_plan.items) == 1
        assert requests == ["FeedDecisionDraft", "InboxTargetSelector", "InboxDecisionDraft"]
        assert db.scalar(select(func.count(models.SocialEvent.id)).where(models.SocialEvent.event_type == "joint_started")) == 0
    engine.dispose()


def test_late_first_plan_does_not_materialize_an_expired_unlinked_reservation(tmp_path):
    from scripts.evaluate_daily_joint_feed import confirmed_reservation
    engine = database(tmp_path / "late-reservation.sqlite3")
    with Session(engine, expire_on_commit=False) as db:
        world, first, second = pair(db)
        now = _utc(datetime.combine(datetime.now(UTC).date()+timedelta(days=3), datetime.min.time())+timedelta(hours=7))
        joint = confirmed_reservation(db, world, first, second, now)
        joint.target_daypart, joint.eligible_dayparts = "dawn", ["dawn"]
        joint.scheduled_start_at, joint.scheduled_end_at = store.daypart_windows(joint.scheduled_local_date, world.timezone)["dawn"]
        db.commit()
        scope = PlanScope(world, first.membership, first.world_character, first.character,
            environment_snapshot(db, first.user.id))
        source, _, before, allowed = preparation._source(db, scope, now)
        assert "dawn" in source["generated_dayparts"] and source["confirmed_reservations"] == []
        full = store.compose_generated_plan(new_output(source).daily_plan,
            generated_dayparts=source["generated_dayparts"], fixed_items=source["fixed_items"], allowed_places=allowed)
        plan = store.apply_plan(db, scope=scope, output=full, target_date=joint.scheduled_local_date,
            now=now, source_digest="c"*64, expected_snapshot=before)
        db.commit()
        rows = store.current_items(db, plan.id)
        assert len(rows) == 4 and all(row.joint_activity_id is None for row in rows)
        assert next(row for row in rows if row.daypart == "dawn").status == "skipped"
        assert all(row.linked_daily_activity_plan_item_id is None for row in db.scalars(select(models.JointActivityParticipant)))
        assert db.scalar(select(func.count(models.SocialEvent.id)).where(models.SocialEvent.event_type == "joint_started")) == 0
    engine.dispose()


def test_acceptance_during_generation_fences_apply_and_keeps_both_reserved_plans(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", True)
    engine = database(tmp_path / "acceptance-race.sqlite3")
    with Session(engine, expire_on_commit=False) as db:
        world, first, second = pair(db)
        now = _utc(datetime.combine(datetime.now(UTC).date()+timedelta(days=3), datetime.min.time())+timedelta(hours=7))
        target = now.astimezone(ZoneInfo(world.timezone)).date()
        for ready in (first, second):
            save_plan(db, world, ready, target, now)
        root = _post(db, post_id="race-root", fixture=second, body="정원에서 쉬고 싶어.", created_at=now)
        invitation = _post(db, post_id="race-invite", fixture=first, body="저녁에 정원에서 함께 쉴래?",
            created_at=now, reply_to_post_id=root.id)
        evidence = _record_post_event(db, world_id=world.id, actor_world_character_id=first.world_character.id,
            target_world_character_id=second.world_character.id, event_type="joint_proposed", source=invitation,
            target_post_id=root.id, root_post_id=root.id, occurred_at=now, idempotency_key="race-proposed",
            interaction_intent="joint_activity_proposal")
        proposal = proposals.create_published_proposal(db, preview=JointActivityProposalPreview(
            text=invitation.body, source_post_id=root.id, activity_seed="정원에서 함께 휴식",
            target_world_character_id=second.world_character.id, target_daypart="evening",
            date_policy="exact", target_date=target), proposal_comment=invitation, proposal_event=evidence,
            proposer_world_character_id=first.world_character.id, now=now)
        db.commit()
        calls = []
        async def generate(**kwargs):
            kwargs["reserve"]()
            calls.append(kwargs["source"])
            with Session(engine) as writer:
                def accept():
                    schedule = proposals.resolve_acceptance_schedule(writer, proposal_id=proposal.id, now=now)
                    reply = _post(writer, post_id="race-accepted", fixture=second, body="좋아, 저녁에 만나자.",
                        created_at=now, reply_to_post_id=invitation.id)
                    event = _record_post_event(writer, world_id=world.id, actor_world_character_id=second.world_character.id,
                        target_world_character_id=first.world_character.id, event_type="joint_accepted", source=reply,
                        target_post_id=invitation.id, root_post_id=root.id, occurred_at=now,
                        idempotency_key="race-accepted", proposal_decision="accept")
                    proposals.apply_response(writer, proposal_id=proposal.id, response_event=event,
                        decision="accept", now=now, resolved_schedule=schedule)
                run_sqlite_session_immediate(writer, accept, require_clean=True)
            return new_output(kwargs["source"]), SimpleNamespace(calls=[])
        from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
        monkeypatch.setattr(preparation.CredentialResolver, "resolve_llm_credential", lambda *a, **k:
            CredentialMaterial("race-credential", "google", "gemini-3.1-flash-lite", "fake",
                CredentialPurpose.WORLD_CHARACTER_SETUP_LLM, "unused"))
        result = asyncio.run(preparation.ensure_preparation(db, character_id=first.character.id, world_id=world.id,
            user=first.user, request_id="acceptance-race", now=now, generator=generate))
        assert len(calls) == 1 and result.request_reason_code == "preparation_source_changed"
        db.expire_all()
        joint = db.scalar(select(models.JointActivity))
        assert joint.status == "ready"
        for ready in (first, second):
            rows = store.current_items(db, store.current_plan(db, ready.world_character.id, target).id)
            assert len(rows) == 4 and sum(row.joint_activity_id == joint.id for row in rows) == 1
        assert db.scalar(select(func.count(models.JointActivityParticipant.world_character_id))) == 2
    engine.dispose()
