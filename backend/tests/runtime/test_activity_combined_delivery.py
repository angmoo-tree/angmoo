import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.social.models.feed import WorldCharacterFeedCursor, WorldCharacterFeedObservation
from app.domains.social.models.topics import RecommendationDelivery
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.combined_lanes import CombinedFeedLane
from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from app.runtime.autonomous_activity import feed
from social.test_feed_reaction_intent import _engine, _seed


def fixture(db):
    ctx, post = _seed(db, with_candidate=True)
    actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
    run = bind_run(db, actor=actor, activity_id=ctx.run_id)
    run.contract_version = 2
    db.commit()
    async def guard(_):
        return {}
    lane = CombinedFeedLane(ctx, actor=actor, lane="feed", tracker=RunLlmTracker(),
        hybrid_service=None, guard=guard, ledger=RecoveryLedger(db, ctx.run_id))
    state = {"identity": {"activity_id": ctx.run_id, "contract_version": 2}, "shared_context": {}}
    return lane, state, run, post


def test_feed_claims_and_snapshot_recover_after_commit_before_parent_checkpoint(monkeypatch):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, run, post = fixture(db)
            prepared = await lane.load(state)
            assert prepared["candidates"][0]["target_id"] == post.id
            assert run.result["feed_preparation"] == prepared
            db.expire_all()
            def forbidden(*args, **kwargs):
                pytest.fail("resuming committed preparation must not search or claim again")
            monkeypatch.setattr(feed, "search_world_feed_candidates", forbidden)
            assert await lane.load(state) == prepared
            assert db.scalar(select(func.count(WorldCharacterFeedObservation.id))) == 1
    asyncio.run(scenario())


def test_failed_preparation_rolls_back_cursor_and_claim_together(monkeypatch):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, run, _post = fixture(db)
            original = feed.search_world_feed_candidates
            def broken(*args, **kwargs):
                raise RuntimeError("synthetic preparation interruption")
            monkeypatch.setattr(feed, "search_world_feed_candidates", broken)
            with pytest.raises(RuntimeError):
                await lane.load(state)
            db.rollback()
            assert db.get(WorldCharacterFeedCursor, lane.actor.id) is None
            assert not (run.result or {}).get("feed_preparation")
            monkeypatch.setattr(feed, "search_world_feed_candidates", original)
            assert (await lane.load(state))["candidates"]
    asyncio.run(scenario())


def test_writer_only_repair_preserves_decision_and_durable_budget(monkeypatch):
    from copy import deepcopy
    from app.runtime.autonomous_activity import provider as transport
    from runtime.test_activity_combined_contracts import assignment

    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, _state, run, _post = fixture(db)
            async def guard(_):
                return {}
            lane.guard = guard
            requests = []
            async def generate(**kwargs):
                requests.append(kwargs)
                return kwargs["validator"]({"replies": [{"task_id": "canonical-p", "body": "힘내세요!"}]})
            monkeypatch.setattr(transport, "generate_json", generate)
            monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic")
            monkeypatch.setattr(transport, "_llm_context", lambda *a, **k: None)
            state = {"generation_mode": "combined", "decision": {
                "decisions": [{"target_id": "p", "action": "comment", "brief": "응원"}],
                "provisional_draft": {"replies": [{"target_id": "p"}]}},
                "decision_context": {}, "assignments": [assignment()], "decision_input_receipt": {}}
            before = deepcopy(state["decision"])
            result = await lane.write(state)
            assert state["decision"] == before
            assert len(requests) == 1
            assert '"assignments"' in requests[0]["user_prompt"]
            assert "decision" not in requests[0]["response_schema"]["properties"]
            assert result["drafts"][0]["body"] == "힘내세요!"
            assert result["writer_input_receipts"][0]["writer_recovery"] is True
            db.expire_all()
            assert len(run.result["recovery_reservations"]) == 1
            lane.provider.ledger = RecoveryLedger(db, run.activity_id)
            with pytest.raises(ValueError, match="recovery_exhausted"):
                await lane.write(state)
            assert len(requests) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("deleted", [False, True])
def test_pending_delivery_survives_retention_then_reconciles_once(deleted):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, _run, post = fixture(db)
            state.update(await lane.load(state))
            delivery = lane.delivery(state)
            delivery.dispatched()
            delivery.delivered()
            identifier = delivery.row.id
            delivery.row.updated_at = datetime.now(UTC) - timedelta(days=40)
            db.commit()
            # Constructing another delivery runs retention; pending delivered
            # evidence must survive even beyond the normal age horizon.
            lane.delivery(state)
            assert db.get(RecommendationDelivery, identifier) is not None
            delivered_at = delivery.row.updated_at.replace(tzinfo=UTC)
            if deleted:
                post.deleted_at = datetime.now(UTC)
                db.commit()
            lane.reconcile_deliveries()
            saved = db.get(RecommendationDelivery, identifier)
            assert saved.updated_at.replace(tzinfo=UTC) == delivered_at
            assert saved.trace["_activity_observation"] == "settled"
            result = saved.trace["_activity_observation_results"][post.id]
            assert result["status"] == ("not_applied" if deleted else "observed")
            if deleted:
                assert result["reason"] == "evidence_source_deleted"
            trace = dict(saved.trace)
            lane.reconcile_deliveries()
            assert saved.trace == trace
    asyncio.run(scenario())


def test_default_rollback_still_reconciles_older_version_two_delivery():
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, _run, post = fixture(db)
            state.update(await lane.load(state))
            delivery = lane.delivery(state)
            delivery.dispatched()
            delivery.delivered()
            assert delivery.row.trace["_activity_observation"] == "pending"
            # New work may use version one after a rollback. The common Feed
            # entry must still settle an older delivered version-two receipt.
            old = feed.FeedLane(lane.ctx, actor=lane.actor, lane="feed", tracker=RunLlmTracker(),
                hybrid_service=None, guard=lane.scope_guard)
            await old.load({**state, "identity": {**state["identity"], "contract_version": 1}})
            assert delivery.row.trace["_activity_observation_results"][post.id]["status"] == "observed"
    asyncio.run(scenario())


def test_delivery_completion_cannot_overwrite_a_replaced_claim():
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, _run, _post = fixture(db)
            state.update(await lane.load(state))
            delivery = lane.delivery(state)
            delivery.dispatched()
            observation = db.scalar(select(WorldCharacterFeedObservation))
            observation.claim_token = "replacement-token"
            observation.run_id = "replacement-run"
            db.commit()
            with pytest.raises(ValueError, match="feed_claim_changed"):
                delivery.delivered()
            assert observation.status == "claimed"
            assert observation.claim_token == "replacement-token"
            assert delivery.row.state == "dispatched"
    asyncio.run(scenario())
