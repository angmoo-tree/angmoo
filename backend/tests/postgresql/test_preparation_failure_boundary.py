"""Actual PostgreSQL failure completion owns one bounded transaction."""
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from postgresql.test_activity_transactions import store
from routines import test_daily_preparation as fixture_source
from app.domains.routines.client import PreparationTracker
from app.domains.routines.models.preparation import ActivityPreparationJob
from app.domains.routines.models.plans import DailyActivityPlan
from app.domains.social.models.topics import RecommendationTopic


@pytest.mark.parametrize('failure', ['provider_error', 'provider_timeout', 'expired_claim', 'invalid_binding'])
def test_preparation_failure_is_durable_without_nested_writer(store, monkeypatch, deny_external_network, failure):
    engine, _, _ = store
    monkeypatch.setattr(fixture_source, '_engine', lambda: engine)
    fixture = fixture_source.preparation_scope.__wrapped__(monkeypatch, deny_external_network)
    db, world, ready, runtime = next(fixture)
    ids = dict(character_id=ready.character.id, world_id=world.id, user=SimpleNamespace(id=ready.user.id))
    models = (DailyActivityPlan, RecommendationTopic)
    before = [db.scalar(select(func.count()).select_from(model)) for model in models]
    db.rollback()
    calls = []
    if failure == 'invalid_binding':
        from app.contracts import name_binding
        def invalid(_):
            raise name_binding.NameBindingError('name_binding_invalid')
        monkeypatch.setattr(name_binding, 'read_name_binding', invalid)
    async def generate(**kwargs):
        tracker = PreparationTracker(kwargs['reserve'])
        await tracker.reserve_provider_call_order()
        assert engine.pool.checkedout() == 0
        calls.append(1)
        if failure == 'provider_timeout':
            raise TimeoutError('synthetic provider timeout')
        raise RuntimeError('synthetic generation failure')
    now = datetime.now(UTC) - (timedelta(minutes=20) if failure == 'expired_claim' else timedelta())
    arguments = dict(**ids, request_id='failure-' + failure, generator=generate, now=now)
    expected_state = 'waiting' if failure == 'provider_timeout' else 'failed'
    expected_code = {'provider_error': 'preparation_generation_failed', 'provider_timeout': 'provider_timeout',
        'expired_claim': 'preparation_attempts_exhausted', 'invalid_binding': 'name_binding_invalid'}[failure]
    try:
        result = asyncio.run(runtime.ensure_preparation(db, **arguments))
        assert result.request_state == expected_state
        assert result.request_reason_code == expected_code
        assert engine.pool.checkedout() == 0 and not db.in_transaction()
        job = db.scalar(select(ActivityPreparationJob).where(ActivityPreparationJob.request_id == arguments['request_id']))
        assert job.state == expected_state and job.reason_code == expected_code
        assert job.lease_expires_at is None
        assert job.attempt_count == (1 if failure.startswith('provider_') else 0)
        assert (job.next_retry_at is not None) == (failure == 'provider_timeout')
        assert [db.scalar(select(func.count()).select_from(model)) for model in models] == before
        db.rollback()
        again = asyncio.run(runtime.ensure_preparation(db, **arguments))
        assert again.request_state == expected_state
        assert calls == ([1] if failure.startswith('provider_') else [])
        assert engine.pool.checkedout() == 0 and not db.in_transaction()
    finally:
        fixture.close()
