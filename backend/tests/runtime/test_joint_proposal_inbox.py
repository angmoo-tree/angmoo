"""Bounded Inbox preparation preserves original proposal targets and alarms."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.runtime.autonomous_activity.combined_lanes import CombinedInboxLane
from app.runtime.activity_proposals import composition as proposals
from relationships.test_activity_proposals import _published_proposal_fixture, _post, _record_post_event
from routines.test_daily_activity_runtime import _engine, _utc


def fixture(db, *, prefix="inbox-proposal"):
    now = _utc(datetime(2026, 8, 9, 9))
    value = _published_proposal_fixture(db, now=now, prefix=prefix)
    db.add(models.CharacterActiveWorld(character_id=value.acceptor.character.id,
        world_character_id=value.acceptor.world_character.id, selected_at=now, idempotency_key=prefix, version=1))
    db.commit()
    return value, now


def notify(db, value, post, when):
    row = models.Notification(recipient_character_id=value.acceptor.character.id,
        actor_character_id=value.proposer.character.id, world_id=value.world.id,
        recipient_world_character_id=value.acceptor.world_character.id,
        actor_world_character_id=value.proposer.world_character.id,
        notification_type="reply", post_id=value.root.id, source_post_id=post.id, created_at=when)
    db.add(row)
    db.commit()
    return row


def lane(db, value):
    adapter = CombinedInboxLane.__new__(CombinedInboxLane)
    adapter.actor = value.acceptor.world_character
    adapter.lane = "inbox"
    adapter.ctx = SimpleNamespace(db=db, run_id="inbox-test-run", character=value.acceptor.character,
        activity_policy=SimpleNamespace(allowed_actions={"reply", "like"}))
    adapter.relationship = lambda _: {}
    async def guard(_):
        return {}
    adapter.scope_guard = guard
    return adapter


@pytest.mark.parametrize("reverse", [False, True])
def test_proposal_and_later_ordinary_comment_have_disjoint_targets_and_alarms(reverse):
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        value, now = fixture(db)
        later = _post(db, post_id="ordinary-later", fixture=value.proposer, body="Nice photo.",
            created_at=now+timedelta(minutes=2), reply_to_post_id=value.root.id)
        rows = [(value.proposal_comment, 1), (later, 2)]
        if reverse:
            rows.reverse()
        notifications = {post.id: notify(db, value, post, now+timedelta(minutes=minutes)) for post, minutes in rows}
        adapter = lane(db, value)
        state = asyncio.run(adapter.load({}))
        assert len(state["candidates"]) == 2
        proposal = next(row for row in state["candidates"] if row["activity_proposal"])
        ordinary = next(row for row in state["candidates"] if not row["activity_proposal"])
        assert proposal["source_ids"] == [value.proposal_comment.id]
        assert ordinary["source_ids"] == [later.id]
        assert proposal["activity_proposal"]["proposal_id"] == value.proposal.id
        assert state["lane_data"][proposal["target_id"]]["post_id"] == value.proposal_comment.id
        assert state["lane_data"][proposal["target_id"]]["notification_ids"] == [notifications[value.proposal_comment.id].id]
        assert state["lane_data"][ordinary["target_id"]]["notification_ids"] == [notifications[later.id].id]
        assert len({alarm for data in state["lane_data"].values() for alarm in data["notification_ids"]}) == 2
        # Explicit no_action consumes only the selected ordinary conversation.
        asyncio.run(adapter.finalize({**state, "executions": [{"target_id": ordinary["target_id"], "status": "no_action"}],
            "selections": [{"target_id": ordinary["target_id"]}]}))
        assert notifications[later.id].handled_at is not None
        assert notifications[value.proposal_comment.id].handled_at is None
    engine.dispose()


@pytest.mark.parametrize("decision", [None, "accept"])
def test_old_writer_checkpoint_uses_only_its_frozen_proposal_when_responding(decision):
    from app.runtime.autonomous_activity.provider import parse_writer_output
    task = {"task_id": "old-inbox-task", "target_post_id": "original-comment", "scope": "inbox", "action_index": 0,
        "source": {"activity_proposal": {"proposal_id": "accepted-original-id", "version": 1}},
        "proposal_response": {"proposal_decision": decision} if decision else None}
    result = parse_writer_output({"replies": [{"task_id": task["task_id"], "body": "좋아, 저녁에 만나자.",
        "proposal_decision": decision}]}, lane="inbox", assignments=[task])["reply_task_results"][0]
    response = result.get("proposal_response")
    if decision:
        assert response["proposal_id"] == "accepted-original-id" and response["decision"] == decision
    else:
        assert response is None


def test_counter_original_survives_later_comment_and_failed_or_unselected_run():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        value, now = fixture(db, prefix="inbox-counter")
        counter = _post(db, post_id="counter-original", fixture=value.acceptor,
            body="다음날 저녁에 정원에서 쉬자.", created_at=now, reply_to_post_id=value.proposal_comment.id)
        response = _record_post_event(db, world_id=value.world.id,
            actor_world_character_id=value.acceptor.world_character.id,
            target_world_character_id=value.proposer.world_character.id, event_type="joint_proposed",
            source=counter, target_post_id=value.proposal_comment.id, root_post_id=value.root.id,
            occurred_at=now, idempotency_key="counter-original", proposal_decision="counter",
            interaction_intent="proposal_response")
        changed = proposals.apply_response(db, proposal_id=value.proposal.id, response_event=response,
            decision="counter", now=now, counter_activity_seed="정원에서 쉬기",
            counter_target_daypart="evening", counter_date_policy="exact",
            counter_target_date=now.date()+timedelta(days=1))
        recipient = SimpleNamespace(world=value.world, root=value.root,
            proposer=value.acceptor, acceptor=value.proposer)
        db.add(models.CharacterActiveWorld(character_id=value.proposer.character.id,
            world_character_id=value.proposer.world_character.id, selected_at=now, idempotency_key="counter-recipient", version=1))
        db.commit()
        original_alarm = notify(db, recipient, counter, now)
        later = _post(db, post_id="after-counter", fixture=value.acceptor, body="사진도 마음에 들어.",
            created_at=now+timedelta(minutes=1), reply_to_post_id=value.proposal_comment.id)
        later_alarm = notify(db, recipient, later, now+timedelta(minutes=1))
        another_branch = _post(db, post_id="another-branch", fixture=value.acceptor, body="별도 가지의 이야기",
            created_at=now+timedelta(minutes=2), reply_to_post_id=value.root.id)
        branch_alarm = notify(db, recipient, another_branch, now+timedelta(minutes=2))
        adapter = lane(db, recipient)
        state = asyncio.run(adapter.load({}))
        assert len(state["candidates"]) == 3
        original = next(row for row in state["candidates"] if row["activity_proposal"])
        assert original["activity_proposal"]["proposal_id"] == changed.child_proposal.id
        assert original["source_ids"] == [counter.id]
        assert state["lane_data"][original["target_id"]]["notification_ids"] == [original_alarm.id]
        asyncio.run(adapter.finalize({**state, "executions": []}))
        asyncio.run(adapter.finalize({**state, "executions": [{"target_id": original["target_id"], "status": "failed"}]}))
        assert all(alarm.handled_at is None for alarm in (original_alarm, later_alarm, branch_alarm))
        assert db.scalar(select(models.JointActivity)) is None
    engine.dispose()


@pytest.mark.parametrize("state", ["expired", "rejected"])
def test_closed_proposal_is_not_presented_as_an_open_invitation(state):
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        value, now = fixture(db, prefix=f"closed-{state}")
        alarm = notify(db, value, value.proposal_comment, now)
        value.proposal.status = state
        db.commit()
        result = asyncio.run(lane(db, value).load({}))
        assert all(candidate["activity_proposal"] is None for candidate in result["candidates"])
        assert alarm.handled_at is None
    engine.dispose()


def test_notification_cap_leaves_proposal_beyond_page_pending_then_visible():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        value, now = fixture(db, prefix="inbox-page")
        earlier = []
        for index in range(10):
            post = _post(db, post_id=f"before-{index}", fixture=value.proposer, body=f"ordinary {index}",
                created_at=now, reply_to_post_id=value.root.id)
            earlier.append(notify(db, value, post, now+timedelta(seconds=index)))
        proposal_alarm = notify(db, value, value.proposal_comment, now+timedelta(minutes=1))
        adapter = lane(db, value)
        first = asyncio.run(adapter.load({}))
        assert all(row["activity_proposal"] is None for row in first["candidates"])
        assert sum(len(row["notification_ids"]) for row in first["lane_data"].values()) == 10
        assert proposal_alarm.handled_at is None
        target = first["candidates"][0]["target_id"]
        asyncio.run(adapter.finalize({**first, "executions": [{"target_id": target, "status": "no_action"}]}))
        second = asyncio.run(adapter.load({}))
        assert second["candidates"][0]["activity_proposal"]["proposal_id"] == value.proposal.id
        assert all(row.handled_at for row in earlier) and proposal_alarm.handled_at is None
    engine.dispose()


def test_closed_or_changed_proposal_cannot_be_dispatched_from_new_snapshot():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        value, now = fixture(db, prefix="inbox-guard")
        alarm = notify(db, value, value.proposal_comment, now+timedelta(minutes=1))
        adapter = lane(db, value)
        state = asyncio.run(adapter.load({}))
        target = state["candidates"][0]["target_id"]
        value.proposal.version += 1
        db.commit()
        with pytest.raises(ValueError, match="activity_proposal_changed"):
            asyncio.run(adapter.guard({**state, "stage": "Execute", "selections": [{"target_id": target}]}))
        assert alarm.handled_at is None
    engine.dispose()
