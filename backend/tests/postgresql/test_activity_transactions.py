"""Real PostgreSQL conflicts at SNS ownership/receipt boundaries; no provider I/O."""
import asyncio
import os
import sqlite3
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, text, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from psycopg.errors import SerializationFailure

from app.config import settings
from app.core.activity_transactions import activity_write
from app.core.postgresql_concurrency import PostgresCommitOutcomeUnknown, PostgresRetryExhausted, sqlstate
from app.database import create_database_engine
from app.core.postgresql_capacity import PostgresPoolSettings
from app.domains.routines.models import AgentSlot
from app.domains.social.models.posts import PostLike
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run, set_engine
from app.runtime.autonomous_activity import binding, postgresql_checkpoints
from app.runtime.autonomous_activity.execution import ActivityScopeChangedError, run_personalized_activity
from app.runtime.autonomous_activity.planner_contract import parse_action
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from app.runtime.persistence.postgresql_schema import initialize
from social.test_feed_reaction_intent import _seed


@pytest.fixture
def store(tmp_path, monkeypatch):
    raw = os.environ.get('ANGMOO_EXPERIMENT_DATABASE_URL')
    if not raw:
        pytest.skip('explicit isolated PostgreSQL DSN required')
    url = make_url(raw)
    assert (url.host, url.port, url.database, url.username) == (
        '127.0.0.1', 15414, 'angmoo_pg_run01', 'angmoo_pg_run01_admin')
    admin = create_database_engine(raw)
    schema = 'sns_retry_' + uuid.uuid4().hex
    with admin.begin() as connection:
        assert connection.execute(text('SELECT run_id FROM angmoo_experiment_identity')).scalar_one() == 'angmoo-pg-20261027-run01'
        connection.exec_driver_sql(f'CREATE SCHEMA {schema}')
    # Exclude public: create_all's existence check otherwise sees the shared
    # experiment tables and can silently skip creating isolated fixture tables.
    scoped = url.update_query_dict({'options': f'-csearch_path={schema}'})
    # Keep the constrained-pool fixture explicit as product capacity increases.
    engine = create_database_engine(scoped.render_as_string(hide_password=False),
        postgresql_pool=PostgresPoolSettings(size=4, overflow=0))
    with engine.begin() as connection:
        initialize(connection)
        assert connection.execute(text("SELECT table_schema FROM information_schema.tables WHERE table_name='users' AND table_schema=current_schema()")).scalar_one() == schema
    checkpoint_dsn = scoped.set(drivername='postgresql').render_as_string(hide_password=False)
    postgresql_checkpoints.initialize(checkpoint_dsn)
    checkpoint = postgresql_checkpoints.PostgresCheckpointStore(checkpoint_dsn)
    postgresql_checkpoints.register(tmp_path, checkpoint)
    def forbidden(*args, **kwargs):
        raise AssertionError('SNS PostgreSQL test opened SQLite')
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    monkeypatch.setattr(settings, 'DAILY_PREPARATION_ENABLED', False)
    yield engine, checkpoint, tmp_path
    postgresql_checkpoints.unregister(tmp_path, checkpoint)
    engine.dispose()
    # This DB has the phone's small lock budget. Drop only this fixture's
    # tables in individual transactions instead of locking 181 tables at once.
    with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        tables = connection.execute(text('SELECT tablename FROM pg_tables WHERE schemaname=:schema'), {'schema': schema}).scalars().all()
        for table in tables:
            assert table.replace('_', '').isalnum()
            connection.exec_driver_sql(f'DROP TABLE "{schema}"."{table}" CASCADE')
        connection.exec_driver_sql(f'DROP SCHEMA {schema} CASCADE')
    admin.dispose()


def seed(db):
    ctx, post = _seed(db, with_candidate=True)
    actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
    db.add(AgentSlot(agent_id=ctx.agent_id, status='running', locked_by_run_id=ctx.run_id,
        assigned_character_id=ctx.character.id, assigned_user_id=ctx.user_id,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=10)))
    set_engine(db, engine='personalized_graph_v2', expected_version=0)
    run = bind_run(db, actor=actor, activity_id=ctx.run_id)
    run.result = {**(run.result or {}), 'reason': 'OperationalError', 'storage_sqlstate': '40001'}
    db.commit()
    return ctx, post, actor, run


def execute(coro):
    return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop if sys.platform == 'win32' else None)


@pytest.mark.parametrize('conflict_at,lose_claim', [('lease', False), ('lease', True), ('delivery', False), ('finalize', False)])
def test_real_serialization_conflict_revalidates_lease_and_never_repeats_provider(store, monkeypatch, conflict_at, lose_claim):
    engine, checkpoint, root = store
    calls, conflicts = [], []
    async def scenario():
        with Session(engine, expire_on_commit=False) as db:
            ctx, post, actor, run = seed(db)
            injected = False
            def concurrent_owner(connection, cursor, statement, parameters, context, many):
                nonlocal injected
                matches = (statement.startswith('UPDATE agent_slots SET lease_expires_at') if conflict_at == 'lease' else
                    statement.startswith('UPDATE social_recommendation_deliveries SET') if conflict_at == 'delivery' else
                    statement.startswith('UPDATE activity_graph_runs SET') and 'finished_at=' in statement)
                if injected or not matches:
                    return
                injected = True
                # The guard already read this slot. A different committed
                # transaction changes it before its UPDATE: a real 40001.
                with engine.begin() as other:
                    if conflict_at == 'delivery':
                        other.execute(text("UPDATE social_recommendation_deliveries SET updated_at=updated_at + interval '1 second'"))
                    elif conflict_at == 'finalize':
                        other.execute(text("UPDATE activity_graph_runs SET result=result || jsonb_build_object('concurrent_metadata',true) WHERE activity_id=:id"), {'id': run.activity_id})
                    else:
                        sql = ('UPDATE agent_slots SET locked_by_run_id=NULL WHERE agent_id=:id' if lose_claim else
                            "UPDATE agent_slots SET lease_expires_at=lease_expires_at + interval '1 second' WHERE agent_id=:id")
                        other.execute(text(sql), {'id': ctx.agent_id})
            def error(context):
                conflicts.append(sqlstate(context.original_exception))
            event.listen(engine, 'before_cursor_execute', concurrent_owner)
            event.listen(engine, 'handle_error', error)
            async def plan(self, **kwargs):
                calls.append('provider')
                kwargs['delivery'].dispatched()
                kwargs['delivery'].delivered()
                return {**parse_action({'decisions': [{'target_id': post.id, 'action': 'like', 'brief': 'Useful discovery'}]}, kwargs['candidates']),
                    'judged_at': datetime.now(UTC).isoformat(), 'provisional_draft': {'replies': []}}
            monkeypatch.setattr(ActivityProvider, 'plan', plan)
            runtime = binding.ActivityRuntimeBinding(None, root)
            binding.register(runtime)
            try:
                if lose_claim:
                    with pytest.raises(ActivityScopeChangedError, match='activity_claim_lost'):
                        await run_personalized_activity(ctx, actor=actor, run=run)
                    assert calls == []
                    assert db.scalar(select(func.count(PostLike.id))) == 0
                else:
                    result = await run_personalized_activity(ctx, actor=actor, run=run)
                    assert result['status'] == 'completed', result
                    assert result['publish_result']['public_action_count'] == 1
                    assert calls == ['provider']
                    assert 'reason' not in run.result and 'storage_sqlstate' not in run.result
                    assert await run_personalized_activity(ctx, actor=actor, run=run) == result
                    assert calls == ['provider']
                    assert db.scalar(select(func.count(PostLike.id))) == 1
                    if conflict_at == 'finalize':
                        assert run.result['concurrent_metadata'] is True
                assert injected and '40001' in conflicts
            finally:
                binding.unregister(runtime)
                event.remove(engine, 'before_cursor_execute', concurrent_owner)
                event.remove(engine, 'handle_error', error)
                await checkpoint.close()
    execute(scenario())


def test_commit_abort_reloads_metadata_and_reserves_only_once(store):
    engine, _, _ = store
    with Session(engine, expire_on_commit=False) as db:
        _, _, _, row = seed(db)
        identifier = row.activity_id
        commits = []
        def abort_once(connection):
            commits.append(1)
            if len(commits) == 1:
                raise OperationalError('COMMIT', {}, SerializationFailure('injected commit abort'))
        event.listen(engine, 'commit', abort_once)
        try:
            RecoveryLedger(db, identifier).reserve_normal('one-physical-send')
        finally:
            event.remove(engine, 'commit', abort_once)
        assert len(commits) == 2
        db.refresh(row)
        assert row.result['normal_reservations'] == ['one-physical-send']
        with pytest.raises(ValueError, match='activity_recovery_exhausted'):
            RecoveryLedger(db, identifier).reserve_normal('one-physical-send')


def test_unknown_commit_is_never_replayed(store):
    engine, _, _ = store
    with Session(engine) as db:
        _, _, _, row = seed(db)
        calls = []
        def operation():
            calls.append(1)
            row.stage = 'fixture'
        def disconnect(connection):
            raise OperationalError('COMMIT', {}, OSError('injected connection loss'))
        event.listen(engine, 'commit', disconnect)
        try:
            with pytest.raises(PostgresCommitOutcomeUnknown):
                activity_write(db, operation)
        finally:
            event.remove(engine, 'commit', disconnect)
        assert calls == [1]


def test_confirmed_abort_stops_after_four_attempts_without_authorizing_a_send(store):
    engine, _, _ = store
    with Session(engine) as db:
        _, _, _, row = seed(db)
        identifier = row.activity_id
        calls = []
        def abort(connection):
            calls.append(1)
            raise OperationalError('COMMIT', {}, SerializationFailure('injected persistent conflict'))
        event.listen(engine, 'commit', abort)
        try:
            with pytest.raises(PostgresRetryExhausted) as error:
                RecoveryLedger(db, identifier).reserve_normal('must-not-send')
            assert sqlstate(error.value) == '40001'
        finally:
            event.remove(engine, 'commit', abort)
        db.refresh(row)
        assert not row.result.get('normal_reservations')
        assert calls == [1, 1, 1, 1]


def test_inbox_publication_and_relationship_settlement_allow_phone_db_cost(store, monkeypatch):
    """A legitimate 350 ms DB unit must not inherit SQLite's 250 ms budget."""
    import time
    from app.domains.social.models.posts import Notification
    from app.runtime.social.planned_actions import _execute_planned_action
    from app.runtime.relationships import social_metrics
    engine, checkpoint, root = store
    async def scenario():
        with Session(engine, expire_on_commit=False) as db:
            ctx, post, actor, run = seed(db)
            db.add(Notification(id=4401, world_id=actor.world_id,
                recipient_world_character_id=actor.id, recipient_character_id=actor.character_id,
                actor_world_character_id=post.author_world_character_id,
                actor_character_id=post.author_character_id, notification_type='mention',
                post_id=post.id, source_post_id=post.id))
            db.commit()
            calls, delayed = [], []
            def phone_cost(connection, cursor, statement, params, context, many):
                if statement.startswith('INSERT INTO post_likes'):
                    delayed.append(statement.split()[2])
                    time.sleep(.35)
            original_staging = social_metrics._stage_sources_in_transaction
            def slow_staging(*args, **kwargs):
                delayed.append('relationship_settlement')
                time.sleep(.35)
                return original_staging(*args, **kwargs)
            monkeypatch.setattr(social_metrics, '_stage_sources_in_transaction', slow_staging)
            event.listen(engine, 'before_cursor_execute', phone_cost)
            async def plan(self, **kwargs):
                lane = kwargs['lane']
                calls.append(lane)
                if kwargs.get('delivery') is not None:
                    kwargs['delivery'].dispatched()
                    kwargs['delivery'].delivered()
                target = kwargs['candidates'][0]['target_id']
                return {**parse_action({'decisions': [{'target_id': target,
                    'action': 'like' if lane == 'inbox' else 'no_action', 'brief': 'Useful discovery'}]}, kwargs['candidates']),
                    'judged_at': datetime.now(UTC).isoformat(), 'provisional_draft': {'replies': []}}
            monkeypatch.setattr(ActivityProvider, 'plan', plan)
            runtime = binding.ActivityRuntimeBinding(None, root)
            binding.register(runtime)
            try:
                result = await run_personalized_activity(ctx, actor=actor, run=run,
                    action_executor=_execute_planned_action)
                assert result['status'] == 'completed', result
                assert result['paths']['inbox']['public_action_count'] == 1, result
                assert db.scalar(select(func.count(PostLike.id))) == 1
                assert calls.count('inbox') == 1
                assert 'post_likes' in delayed and 'relationship_settlement' in delayed
            finally:
                event.remove(engine, 'before_cursor_execute', phone_cost)
                binding.unregister(runtime)
                await checkpoint.close()
    execute(scenario())
