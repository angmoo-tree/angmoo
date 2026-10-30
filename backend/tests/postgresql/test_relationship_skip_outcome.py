"""Injected legacy guard failures retain their reason and never authorize effects.

Ordinary content edits under the new initial-input policy are tested separately;
these cases exercise the graph's ownership of an already raised guard failure.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import pytest

from postgresql.test_activity_transactions import store, seed, execute
from app.domains.social.models.posts import PostLike
from app.runtime.autonomous_activity import binding
from app.runtime.autonomous_activity.execution import run_personalized_activity
from app.runtime.autonomous_activity.inputs import ActivityRelationshipValidationError
from app.runtime.autonomous_activity.social_lane import SocialLane
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.routine import RoutineLane
from app.runtime.autonomous_activity.combined_lanes import CombinedRoutineLane, CombinedInboxLane, CombinedFeedLane


@pytest.mark.parametrize('reason,status', [('version_changed','no_action'),('canonical_read_error','failed')])
@pytest.mark.parametrize('stage', ['RecallSelected', 'DecisionDraft'])
def test_prepublication_guard_outcome_keeps_reason_and_does_not_send(store, monkeypatch, reason, status, stage):
    engine, checkpoint, root = store
    previous = SocialLane.guard
    rejected = []
    async def guard(self, state):
        await previous(self, state)
        if self.lane == 'feed' and state['stage'] == stage:
            rejected.append(state['stage'])
            raise ActivityRelationshipValidationError(reason, lane='feed')
    async def no_provider(*args, **kwargs):
        pytest.fail('A rejected frozen input must not authorize a provider call')
    monkeypatch.setattr(SocialLane, 'guard', guard)
    monkeypatch.setattr(ActivityProvider, 'plan', no_provider)
    async def scenario():
        with Session(engine, expire_on_commit=False) as db:
            ctx, _, actor, run = seed(db)
            runtime = binding.ActivityRuntimeBinding(None, root)
            binding.register(runtime)
            try:
                result = await run_personalized_activity(ctx, actor=actor, run=run)
                assert result['status'] == ('observed' if status == 'no_action' else 'failed')
                db.refresh(run)
                outcome = run.result['paths']['feed']
                assert outcome['status'] == status
                assert outcome['reason'] == 'activity_relationship_changed'
                assert outcome['relationship_validation']['reason'] == reason
                assert outcome.get('policy_outcome') == ('input_changed_before_publication' if status == 'no_action' else None)
                assert db.scalar(select(func.count(PostLike.id))) == 0
                assert len(rejected) == 1
            finally:
                binding.unregister(runtime)
                await checkpoint.close()
    execute(scenario())


@pytest.mark.parametrize('reason,status', [('version_changed','no_action'),('canonical_read_error','failed')])
def test_routine_rejects_changed_input_and_releases_claim_before_publication(store, monkeypatch, reason, status):
    engine, checkpoint, root = store
    releases = []
    async def empty_social(self, state):
        return {'candidates': [], 'selections': []}
    async def routine_load(self, state):
        # A synthetic prepared candidate drives the real graph/error owner.
        from app.runtime.autonomous_activity.initial_input import seal
        return seal(state, {'candidates': [{'target_id':'synthetic-routine'}]})
    async def empty(self, state):
        return {}
    previous = RoutineLane.guard
    async def guard(self, state):
        await previous(self, state)
        if state['stage']=='ValidateDecision':
            raise ActivityRelationshipValidationError(reason,lane='routine')
    async def no_publish(self, state):
        pytest.fail('Rejected routine input cannot publish')
    monkeypatch.setattr(CombinedInboxLane,'load',empty_social)
    monkeypatch.setattr(CombinedFeedLane,'load',empty_social)
    monkeypatch.setattr(CombinedRoutineLane,'load',routine_load)
    for method in ('query','recall','context','plan'):
        monkeypatch.setattr(CombinedRoutineLane,method,empty)
    monkeypatch.setattr(RoutineLane,'guard',guard)
    monkeypatch.setattr(RoutineLane,'release_failed',lambda self,value:releases.append(value))
    monkeypatch.setattr(CombinedRoutineLane,'execute',no_publish)
    async def scenario():
        with Session(engine,expire_on_commit=False) as db:
            ctx,_,actor,run=seed(db)
            runtime=binding.ActivityRuntimeBinding(None,root);binding.register(runtime)
            try:
                result=await run_personalized_activity(ctx,actor=actor,run=run)
                outcome=result['paths']['routine']
                assert outcome['status']==status
                assert outcome['reason']=='routine_relationship_changed'
                assert outcome['failed_stage']=='ValidateDecision'
                assert outcome['relationship_validation']['reason']==reason
                assert outcome.get('policy_outcome')==('input_changed_before_publication' if status=='no_action' else None)
                assert outcome['public_action_count']==0
                assert releases==['routine_relationship_changed']
            finally:
                binding.unregister(runtime)
                await checkpoint.close()
    execute(scenario())
