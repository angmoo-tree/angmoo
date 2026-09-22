import asyncio
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.domains.social.models.posts import Post, Notification
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.service.activity_state import read_state
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.inbox import InboxLane
from app.runtime.autonomous_activity.graph import build_lane
from app.runtime.autonomous_activity.provider import parse_action
from social.test_feed_reaction_intent import _engine, _seed


def test_inbox_selects_one_branch_and_preserves_unselected_and_late_notifications(monkeypatch):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, source = _seed(db, with_candidate=True)
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            other = Post(id="other-branch", world_id=actor.world_id, author_name=source.author_name,
                author_character_id=source.author_character_id, author_world_character_id=source.author_world_character_id,
                title="Other topic", body="A separate conversation.", visibility="public")
            db.add(other); db.flush()
            def notification(post, identifier):
                return Notification(id=identifier, world_id=actor.world_id, recipient_world_character_id=actor.id,
                    recipient_character_id=actor.character_id, actor_world_character_id=source.author_world_character_id,
                    actor_character_id=source.author_character_id, notification_type="mention", post_id=post.id, source_post_id=post.id)
            first, second = notification(source, 1001), notification(other, 1002)
            db.add_all([first, second]); db.commit()
            async def guard(state): return {}
            lane = InboxLane(ctx, actor=actor, lane="inbox", tracker=RunLlmTracker(max_calls=3), hybrid_service=None, guard=guard)
            monkeypatch.setattr(lane, "relationship", lambda _: {})
            async def select(**kwargs):
                target = next(c for c in kwargs["candidates"] if source.id in c["source_ids"])
                return {"selections": [{"target_id": target["target_id"], "memory_query": "past commitments"}]}
            async def plan(**kwargs):
                # A new notification after selection must remain pending.
                db.add(notification(source, 1003)); db.commit()
                return {**parse_action({"decisions": [{"target_id": kwargs["candidates"][0]["target_id"], "action": "no_action"}]}, kwargs["candidates"]), "judged_at": datetime.now(UTC).isoformat()}
            monkeypatch.setattr(lane.provider, "select", select)
            monkeypatch.setattr(lane.provider, "plan", plan)
            result = await build_lane("inbox", lane.ports()).ainvoke({"identity": {"activity_id": ctx.run_id},
                "shared_context": {"current_state": read_state(db, world_id=actor.world_id, actor_id=actor.id)}})
            assert len(result["queries"]) == 1
            assert first.handled_at is not None
            assert second.handled_at is None and db.get(Notification, 1003).handled_at is None
            assert result["result"]["public_action_count"] == 0
    asyncio.run(scenario())


def test_partial_execution_restart_uses_public_success_receipt():
    from sqlalchemy import select, func
    from app.domains.routines.models import AgentPublicActionExecution
    import pytest
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, source = _seed(db, with_candidate=True)
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            second = Post(id="second-reply", world_id=actor.world_id, author_name=source.author_name, author_character_id=source.author_character_id, author_world_character_id=source.author_world_character_id, title="Second", body="Second branch", visibility="public")
            db.add(second); db.commit()
            failed = [False]
            def execute(context, **kwargs):
                post_id = kwargs["action"]["post_id"]
                if post_id == second.id and not failed[0]:
                    failed[0] = True
                    raise RuntimeError("process_exit_after_first_reply")
                row = AgentPublicActionExecution(run_id=ctx.run_id, character_id=ctx.character.id, signature="test:" + post_id, scope="inbox", action_type="reply", target_post_id=post_id, status="succeeded")
                db.add(row); db.commit()
                return {"status":"succeeded", "execution_id":row.id}
            async def guard(state): return {}
            lane = InboxLane(ctx, actor=actor, lane="inbox", tracker=RunLlmTracker(max_calls=3), hybrid_service=None, guard=guard, action_executor=execute)
            state = {"decision":{"decisions":[{"target_id":p.id,"action":"comment","brief":"Reply"} for p in (source,second)]}, "lane_data":{p.id:{"post_id":p.id} for p in (source,second)}, "drafts":[]}
            with pytest.raises(RuntimeError, match="process_exit_after_first_reply"):
                await lane.execute(state)
            result = await lane.execute(state)
            assert [r["status"] for r in result["executions"]] == ["reused", "succeeded"]
            assert db.scalar(select(func.count(AgentPublicActionExecution.id))) == 2
    asyncio.run(scenario())


def test_deleted_notifications_do_not_starve_new_valid_inbox():
    from app.domains.social.service.activity_inbox import pending_conversations
    with Session(_engine(), expire_on_commit=False) as db:
        ctx, source = _seed(db, with_candidate=True)
        actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
        deleted = Post(id="gone", world_id=actor.world_id, author_name=source.author_name, author_character_id=source.author_character_id, author_world_character_id=source.author_world_character_id, title="Deleted", body="deleted", deleted_at=datetime.now(UTC), visibility="public")
        db.add(deleted); db.flush()
        for i in range(12):
            db.add(Notification(id=2000+i,world_id=actor.world_id,recipient_world_character_id=actor.id,recipient_character_id=actor.character_id,actor_world_character_id=source.author_world_character_id,actor_character_id=source.author_character_id,notification_type="mention",post_id=deleted.id if i<11 else source.id,source_post_id=deleted.id if i<11 else source.id))
        db.commit()
        candidates = pending_conversations(db,actor=actor,allowed_actions=ctx.activity_policy.allowed_actions)
        assert len(candidates) == 1
        assert [p.id for p in candidates[0]["posts"]] == [source.id]
