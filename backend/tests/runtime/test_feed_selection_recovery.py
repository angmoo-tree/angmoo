"""Interrupted selector requests retain uncertainty and consume a bounded retry."""
import asyncio
from copy import deepcopy

import pytest
from sqlalchemy.orm import Session

from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from app.runtime.autonomous_activity.output_recovery import RECOVERY_CALL_BUDGET
from app.runtime.autonomous_activity.provider import ActivityProvider
from runtime.test_activity_combined_delivery import fixture
from social.test_feed_reaction_intent import _engine


async def interrupted(db, *, dispatched=False):
    lane, state, run, post = fixture(db)
    state.update(await lane.load(state))
    original = lane.delivery(state)
    original.dispatched()
    if not dispatched:
        original.uncertain()
    run.status, run.stage = "running", "TargetSelector"
    run.result = {**run.result, "normal_reservations": ["original-selector"]}
    db.commit()
    lane.claim_validator = lambda: None
    return lane, {**state, "stage": "TargetSelector"}, run, original


@pytest.mark.parametrize("dispatched", [False, True])
@pytest.mark.parametrize("token_budget", [False, True])
def test_interrupted_selection_retries_once_with_history_and_existing_budget(monkeypatch, dispatched, token_budget):
    from app.contracts.sns_generation import read_generation_policies, new_generation_policies
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, run, original = await interrupted(db, dispatched=dispatched)
            if token_budget:
                lane.provider.generation_policies = read_generation_policies(new_generation_policies())
            delivery = lane.delivery(state)
            before = deepcopy(delivery.row.trace)
            # Discovering a recovery opportunity is not permission to transmit.
            assert delivery.row.state == ("dispatched" if dispatched else "uncertain")
            calls = []
            async def generate(self, **kwargs):
                if token_budget:
                    kwargs["before_admitted_request"]()
                calls.append("request")
                kwargs["delivery"].dispatched()
                kwargs["delivery"].delivered()
                return {"selections": []}
            monkeypatch.setattr(ActivityProvider, "call", generate)
            result = await lane.provider.call(node="FeedTargetSelector", delivery=delivery)
            assert result == {"selections": []} and calls == ["request"]
            db.expire_all()
            assert delivery.row.state == "delivered"
            assert delivery.row.trace["_selection_recovery"]["state"] == ("dispatched" if dispatched else "uncertain")
            assert all(delivery.row.trace[key] == value for key, value in before.items())
            assert run.result["normal_reservations"] == ["original-selector"]
            assert run.result["recovery_reservations"] == [delivery.recovery_key]
            # A late callback from the cancelled attempt cannot overwrite the new one.
            with pytest.raises(ValueError, match="feed_delivery_attempt_changed"):
                original.delivered()
            with pytest.raises(ValueError, match="feed_delivery_attempt_changed"):
                original.uncertain()
            assert delivery.row.state == "delivered"
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["lease", "claim", "completed_path", "budget"])
def test_recovery_rechecks_ownership_and_rolls_back_admission(fault):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, run, original = await interrupted(db)
            delivery = lane.delivery(state)
            if fault == "lease":
                def lost():
                    raise ValueError("activity_claim_lost")
                lane.claim_validator = lost
            elif fault == "claim":
                original.claims.observations[0].claim_token = "new-owner"
            elif fault == "completed_path":
                run.result = {**run.result, "paths": {"inbox": {"status": "completed"}}}
            else:
                run.result = {**run.result, "recovery_reservations": [str(n) for n in range(RECOVERY_CALL_BUDGET)]}
            db.commit()
            before = deepcopy(run.result)
            with pytest.raises(ValueError):
                RecoveryLedger(db, run.activity_id).reserve_delivery_recovery(delivery)
            db.expire_all()
            assert run.result == before
            assert delivery.row.state == "uncertain"
            assert "_selection_recovery" not in delivery.row.trace
    asyncio.run(scenario())


def test_consumed_recovery_is_not_replenished_after_another_interruption():
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, run, original = await interrupted(db)
            delivery = lane.delivery(state)
            RecoveryLedger(db, run.activity_id).reserve_delivery_recovery(delivery)
            # Covers a crash after admission but before actual transmission.
            with pytest.raises(ValueError, match="feed_delivery_recovery_exhausted"):
                lane.delivery(state)
            delivery.dispatched()
            delivery.uncertain()
            with pytest.raises(ValueError, match="feed_delivery_recovery_exhausted"):
                lane.delivery(state)
            assert run.result["recovery_reservations"] == [delivery.recovery_key]
            with pytest.raises(ValueError, match="feed_delivery_requires_reconciliation"):
                lane.delivery({**state, "stage": "DecisionDraft"})
    asyncio.run(scenario())


def test_uncertain_receipt_is_not_pruned_before_recovery():
    from datetime import UTC, datetime, timedelta
    from app.domains.social.models.topics import RecommendationDelivery
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, _, original = await interrupted(db)
            original.row.updated_at = datetime.now(UTC) - timedelta(days=40)
            identifier = original.row.id
            db.commit()
            lane.delivery(state)
            assert db.get(RecommendationDelivery, identifier).state == "uncertain"
    asyncio.run(scenario())
