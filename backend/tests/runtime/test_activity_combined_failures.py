import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domains.routines.models import AgentSlot
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run
from app.runtime.autonomous_activity.binding import ActivityRuntimeBinding, register, unregister
from app.runtime.autonomous_activity import execution
from app.runtime.autonomous_activity.provider import ActivityProvider
from social.test_feed_reaction_intent import _engine, _seed


def test_stale_preselected_feed_finishes_without_reselection_and_routine_continues(monkeypatch, tmp_path):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, post = _seed(db, with_candidate=True)
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            db.add(AgentSlot(agent_id=ctx.agent_id, status="running", locked_by_run_id=ctx.run_id,
                assigned_character_id=ctx.character.id, assigned_user_id=ctx.user_id,
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=10)))
            run = bind_run(db, actor=actor, activity_id=ctx.run_id)
            run.contract_version = 2
            db.commit()
            calls = []
            original = execution.shared_input
            def refreshed(*args, **kwargs):
                calls.append("context")
                if len(calls) == 2:
                    post.deleted_at = datetime.now(UTC)
                    db.commit()
                return original(*args, **kwargs)
            async def no_ai(*args, **kwargs):
                pytest.fail("invalid frozen Feed target must not trigger selection or generation")
            monkeypatch.setattr(execution, "shared_input", refreshed)
            monkeypatch.setattr(ActivityProvider, "call", no_ai)
            binding = ActivityRuntimeBinding(None, tmp_path)
            register(binding)
            try:
                result = await execution.run_personalized_activity(ctx, actor=actor, run=run)
                assert result["paths"]["feed"]["status"] == "no_action"
                assert result["paths"]["feed"]["reason"] == "feed_target_stale"
                assert result["paths"]["feed"]["selected_ids"] == [post.id]
                assert result["paths"]["feed"]["feed_summary"]["reason_code"] == "target_stale"
                from app.domains.social.models.feed import WorldCharacterFeedCursor, WorldCharacterFeedObservation
                from sqlalchemy import select
                cursor = db.get(WorldCharacterFeedCursor, actor.id)
                assert cursor.last_cycle_summary["termination_reason"] == "feed_target_stale"
                observation = db.scalar(select(WorldCharacterFeedObservation))
                assert observation.status == "retryable_failed"
                assert observation.observed_at is None
                assert observation.reason_code == "target_stale"
                assert "routine" in result["paths"]
                assert result["execution_order"] == ["inbox", "feed", "routine"]
                assert result["publish_result"]["public_action_count"] == 0
                assert await execution.run_personalized_activity(ctx, actor=actor, run=run) == result
                assert len(calls) == 3
            finally:
                unregister(binding)
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["autonomy_off", "execution_lease_lost", "feed_claim_replaced"])
def test_preselected_run_rechecks_scope_and_claim_before_any_generation(monkeypatch, tmp_path, change):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, _post = _seed(db, with_candidate=True)
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            slot = AgentSlot(agent_id=ctx.agent_id, status="running", locked_by_run_id=ctx.run_id,
                assigned_character_id=ctx.character.id, assigned_user_id=ctx.user_id,
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=10))
            db.add(slot)
            run = bind_run(db, actor=actor, activity_id=ctx.run_id)
            run.contract_version = 2
            db.commit()
            reads = 0
            original = execution.shared_input
            def refresh(*args, **kwargs):
                nonlocal reads
                reads += 1
                result = original(*args, **kwargs)
                if reads == 2:
                    if change == "autonomy_off":
                        actor.autonomous_enabled = False
                    elif change == "execution_lease_lost":
                        slot.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                    else:
                        from sqlalchemy import select
                        from app.domains.social.models.feed import WorldCharacterFeedObservation
                        claim = db.scalar(select(WorldCharacterFeedObservation))
                        claim.claim_token = "replacement-owner-token"
                    db.commit()
                return result
            async def no_ai(*args, **kwargs):
                pytest.fail("scope or claim change must be checked before model generation")
            monkeypatch.setattr(execution, "shared_input", refresh)
            monkeypatch.setattr(ActivityProvider, "call", no_ai)
            binding = ActivityRuntimeBinding(None, tmp_path)
            register(binding)
            try:
                if change == "feed_claim_replaced":
                    result = await execution.run_personalized_activity(ctx, actor=actor, run=run)
                    assert result["paths"]["feed"]["reason"] == "feed_claim_changed"
                    assert result["paths"]["feed"]["status"] == "no_action"
                    assert "routine" in result["paths"]
                else:
                    with pytest.raises(execution.ActivityScopeChangedError):
                        await execution.run_personalized_activity(ctx, actor=actor, run=run)
                    assert run.status == "aborted"
                    assert "inbox" in run.result["paths"]
                    assert "routine" not in run.result["paths"]
            finally:
                unregister(binding)
    asyncio.run(scenario())
