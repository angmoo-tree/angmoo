"""Real PostgreSQL concurrency and revocation fences for independent chats."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from postgresql.test_activity_transactions import store
from social.test_l4_social_write_uow import _seed
from app.domains.identity.models import InstallationIdentity, User
from app.domains.chat.models import MessageThread
from app.core.database_transactions import postgres_db_unit
from app.domains.chat.service.generation import GenerationService
from app.runtime.chat.message_composition import thread_service, settings_service
from app.runtime.chat import generation_workflows, scope_queries
from app.domains.identity.service.environment import lock_environment_admission


def prepare(engine):
    _seed(sessionmaker(engine, expire_on_commit=False))
    with Session(engine) as db:
        db.merge(InstallationIdentity(singleton_key='local-installation', installation_id='chat-load',
            owner_user_id='social-uow-owner', bootstrap_state='claimed', local_label='load', claimed_at=datetime.now(UTC)))
        for name in ('one',):
            db.add(MessageThread(id='chat-'+name, requester_id='social-uow-owner',
                character_id='social-uow-autonomous-character', world_id='social-uow-world',
                requester_world_character_id='social-uow-owner-actor',
                responding_world_character_id='social-uow-autonomous-actor', world_scope_status='resolved',
                selected_model='gemini-3-flash-preview', selected_thinking_level='high', model_binding_mode='default'))
        db.commit()


def test_parallel_scope_validation_still_fences_revocation(store):
    engine, _, _ = store
    prepare(engine)
    barrier = Barrier(2)
    def validate(_):
        with Session(engine) as db:
            db.execute(text("SET LOCAL lock_timeout='300ms'"))
            assert scope_queries.local_installation(db, lock_scope=True).owner_user_id == 'social-uow-owner'
            assert scope_queries.owned_world_id(db, 'social-uow-owner', 'social-uow-world', lock_scope=True)
            assert len(scope_queries.owner_controlled_world_characters(db, 'social-uow-owner', 'social-uow-world', lock_scope=True)) == 1
            barrier.wait(timeout=5)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(validate, range(2)))
    with Session(engine) as reader:
        scope_queries.owned_world_id(reader, 'social-uow-owner', 'social-uow-world', lock_scope=True)
        with Session(engine) as writer:
            writer.execute(text("SET LOCAL lock_timeout='50ms'"))
            with pytest.raises(OperationalError) as error:
                writer.execute(text("UPDATE worlds SET status='archived' WHERE id='social-uow-world'"))
            assert error.value.orig.sqlstate == '55P03'
    with Session(engine) as db:
        assert scope_queries.owned_world_id(db, 'social-uow-owner', 'social-uow-world') == 'social-uow-world'


def test_status_validation_has_no_global_write_or_row_lock(store):
    engine, _, _ = store
    prepare(engine)
    service = GenerationService(thread_service, settings_service, generation_workflows)
    statements = []
    def record(conn, cursor, sql, params, context, many):
        statements.append(sql.upper())
    event.listen(engine, 'before_cursor_execute', record)
    try:
        with Session(engine) as db:
            owner = db.get(User, 'social-uow-owner')
            service._read_thread(db, owner, 'social-uow-world', 'chat-one')
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    assert not any('UPDATE INSTALLATION_IDENTITIES' in sql or 'FOR UPDATE' in sql or 'FOR SHARE' in sql for sql in statements)


def test_parallel_admissions_share_environment_fence_but_activation_is_exclusive(store):
    engine, _, _ = store
    prepare(engine)
    barrier = Barrier(2)
    def admit(_):
        with Session(engine) as db:
            db.execute(text("SET LOCAL lock_timeout='300ms'"))
            lock_environment_admission(db, 'social-uow-owner')
            barrier.wait(timeout=5)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(admit, range(2)))
    with Session(engine) as admission:
        lock_environment_admission(admission, 'social-uow-owner')
        with Session(engine) as activation:
            activation.execute(text("SET LOCAL lock_timeout='50ms'"))
            with pytest.raises(OperationalError) as error:
                lock_environment_admission(activation, 'social-uow-owner', exclusive=True)
            assert error.value.orig.sqlstate == '55P03'
    with Session(engine) as activation:
        lock_environment_admission(activation, 'social-uow-owner', exclusive=True)
        with Session(engine) as admission:
            admission.execute(text("SET LOCAL lock_timeout='50ms'"))
            with pytest.raises(OperationalError) as error:
                lock_environment_admission(admission, 'social-uow-owner')
            assert error.value.orig.sqlstate == '55P03'
    # A transaction which read before the configuration commit cannot acquire
    # the fence and keep using that stale environment/settings snapshot.
    with Session(engine) as stale:
        stale.scalar(select(InstallationIdentity.singleton_key))
        with Session(engine) as activation:
            lock_environment_admission(activation, 'social-uow-owner', exclusive=True)
            activation.commit()
        with pytest.raises(OperationalError) as error:
            lock_environment_admission(stale, 'social-uow-owner')
        assert error.value.orig.sqlstate == '40001'


def test_chat_db_unit_retries_complete_aborted_decision_and_commits_once(store):
    engine, _, _ = store
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE chat_unit_count (value integer)'))
        conn.execute(text('INSERT INTO chat_unit_count VALUES (0)'))
    attempts = []
    class Admission:
        @postgres_db_unit
        def accept(self, db):
            attempts.append(1)
            db.execute(text('UPDATE chat_unit_count SET value=value+1'))
            if len(attempts) == 1:
                db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'retry' USING ERRCODE='40001'; END $$"))
            db.commit()  # Legacy service commit joins the one outer owner.
            return db.scalar(text('SELECT value FROM chat_unit_count'))
    with Session(engine) as db:
        assert Admission().accept(db) == 1
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT value FROM chat_unit_count')) == 1
    assert len(attempts) == 2


def test_workflow_checkpoint_retries_db_effect_without_repeating_provider(store):
    engine,_,_=store
    with engine.begin() as c:
        c.execute(text('CREATE TABLE workflow_effect(value integer)'))
        c.execute(text('INSERT INTO workflow_effect VALUES (0)'))
    provider_calls=['received response']
    attempts=[]
    with Session(engine) as db:
        uow=generation_workflows.SqlAlchemyResponseWorkflowUnitOfWork(db)
        def store_response():
            attempts.append(1)
            db.execute(text('UPDATE workflow_effect SET value=value+1'))
            if len(attempts)==1:
                db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'retry' USING ERRCODE='40001'; END $$"))
            return provider_calls[0]
        assert uow.run_database_unit(store_response)=='received response'
    with engine.connect() as c:
        assert c.scalar(text('SELECT value FROM workflow_effect'))==1
    assert len(attempts)==2 and len(provider_calls)==1


def test_admission_validates_scope_without_reading_latest_message(store,monkeypatch):
    from app.domains.chat.schemas import WorldChatMessageCreate
    from app.domains.chat.models import MessageMessage,ChatResponseRequest
    from sqlalchemy import func
    engine,_,_=store
    prepare(engine)
    service=GenerationService(thread_service,settings_service,generation_workflows)
    monkeypatch.setattr(service,'_request_names',lambda *args: {})
    monkeypatch.setattr(thread_service,'resolve_world_thread_response_model',lambda *args:'gemini-3-flash-preview')
    statements=[]
    def trace(conn,cursor,sql,params,ctx,many):statements.append(sql.upper())
    event.listen(engine,'before_cursor_execute',trace)
    try:
        with Session(engine) as db:
            owner=db.get(User,'social-uow-owner')
            data=WorldChatMessageCreate(content='synthetic admission',idempotency_key='admission-same-key-001')
            first=service.accept_world_message(db,owner,'social-uow-world','chat-one',data)
            first_statements=list(statements)
            second=service.accept_world_message(db,owner,'social-uow-world','chat-one',data)
            assert first.response_request.request_id==second.response_request.request_id
            assert second.outcome=='replayed'
        insertion=next(i for i,sql in enumerate(first_statements) if sql.startswith('INSERT INTO MESSAGE_MESSAGES'))
        assert not any('FROM MESSAGE_MESSAGES' in sql for sql in first_statements[:insertion])
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(MessageMessage))==1
            assert db.scalar(select(func.count()).select_from(ChatResponseRequest))==1
    finally:
        event.remove(engine,'before_cursor_execute',trace)


def test_provider_boundary_releases_reads_and_defers_failed_diagnostic_to_next_checkpoint(store,monkeypatch):
    from app.contracts.retrieval_observation import Observation, current
    from app.domains.chat.repository import retrieval_diagnostics
    engine,_,_=store
    with engine.begin() as c:
        c.execute(text('CREATE TABLE provider_boundary_effect(value integer)'))
        c.execute(text('INSERT INTO provider_boundary_effect VALUES (0)'))
    calls=[]
    token=current.set(Observation(request_id='provider-boundary-synthetic'))
    try:
        with Session(engine) as db:
            db.scalar(text('SELECT value FROM provider_boundary_effect'))
            # ORM/plain reads may precede this boundary; no uncommitted effect may.
            db.connection().info['angmoo_transaction_written']=False
            uow=generation_workflows.SqlAlchemyResponseWorkflowUnitOfWork(db)
            def save(diagnostic_db, observation):
                assert not db.in_transaction()
                assert diagnostic_db is not db
                calls.append(1)
                diagnostic_db.execute(text('UPDATE provider_boundary_effect SET value=value+1'))
                if len(calls)==1:
                    diagnostic_db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'retry' USING ERRCODE='40001'; END $$"))
            monkeypatch.setattr(retrieval_diagnostics,'save',save)
            uow.checkpoint()
            assert calls==[1] and not db.in_transaction()
            with engine.connect() as c:
                assert c.scalar(text('SELECT value FROM provider_boundary_effect'))==0
            # Disposable capture recovers at the next normal checkpoint. It
            # never replays provider I/O or an authoritative chat transaction.
            uow.checkpoint()
            assert not db.in_transaction()
    finally:
        current.reset(token)
    with engine.connect() as c:
        assert c.scalar(text('SELECT value FROM provider_boundary_effect'))==1
    assert len(calls)==2
    assert engine.pool.checkedout()==0
