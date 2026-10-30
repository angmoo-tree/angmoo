"""Live PostgreSQL contracts; requires the guarded experiment DSN explicitly."""
import os,time,uuid,sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
import pytest
from sqlalchemy import text,select,func,event
from sqlalchemy.exc import IntegrityError,DBAPIError
from app.database import create_database_engine,create_session_factory
from app.core.postgresql_capacity import PostgresPoolSettings
from app.core.sqlite_concurrency import (run_sqlite_immediate,run_sqlite_session_immediate,
    require_read_only_session,SqliteRetryPolicy)
from app.core.postgresql_concurrency import PostgresDeadlineExceeded
from app.core.postgresql_deadline import read_deadline
from app.runtime.persistence.postgresql_schema import metadata
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork
from social.test_l4_social_write_uow import _seed,_owner_post,_autonomous_post
from app.domains.identity.models import User
from app.domains.social.models.posts import Post
from app.domains.worlds.models import World

POLICY=SqliteRetryPolicy(max_attempts=8,maximum_elapsed_seconds=5)

@pytest.fixture(scope='module')
def engine():
    dsn=os.environ.get('ANGMOO_EXPERIMENT_DATABASE_URL')
    if not dsn:pytest.skip('explicit isolated PostgreSQL DSN required')
    from sqlalchemy.engine import make_url
    url=make_url(dsn)
    assert url.host=='127.0.0.1' and url.port==15414 and url.database=='angmoo_pg_run01'
    assert url.username=='angmoo_pg_run01_admin'
    e=create_database_engine(dsn,postgresql_pool=PostgresPoolSettings(size=4,overflow=0))
    with e.begin() as c:
        assert c.execute(text('SELECT run_id FROM angmoo_experiment_identity')).scalar_one()=='angmoo-pg-20261027-run01'
        # Shared synthetic PC fixtures are prepared offline for this source.
        # Serving composition still refuses an un-upgraded v2 database.
        from app.runtime.persistence.postgresql_schema import initialize
        initialize(c)
        c.execute(text('CREATE TABLE IF NOT EXISTS g2_test_counter(id text PRIMARY KEY,value int NOT NULL)'))
    metadata()
    factory=create_session_factory(e)
    with factory() as s:exists=s.get(User,'social-uow-owner') is not None
    if not exists:_seed(factory)
    yield e
    e.dispose()

@pytest.fixture(autouse=True)
def no_sqlite(monkeypatch):
    def forbidden(*a,**k):raise AssertionError('Serving PostgreSQL contract opened SQLite')
    monkeypatch.setattr(sqlite3,'connect',forbidden)

def counter(engine):
    key=uuid.uuid4().hex
    with engine.begin() as c:c.execute(text('INSERT INTO g2_test_counter VALUES(:key,0)'),{'key':key})
    return key

def value(engine,key):
    with engine.connect() as c:return c.execute(text('SELECT value FROM g2_test_counter WHERE id=:key'),{'key':key}).scalar_one()

def test_connection_rollback_and_exception_not_replayed(engine):
    key=counter(engine);calls=[]
    def op(c):
        calls.append(1)
        c.execute(text('UPDATE g2_test_counter SET value=1 WHERE id=:key'),{'key':key})
        raise ValueError('domain_failure')
    with pytest.raises(ValueError,match='domain_failure'):
        run_sqlite_immediate(engine,op,retry_policy=POLICY)
    assert calls==[1] and value(engine,key)==0

def test_deadline_rolls_back_before_publication(engine):
    key=counter(engine)
    def op(c):
        c.execute(text('UPDATE g2_test_counter SET value=1 WHERE id=:key'),{'key':key})
        time.sleep(.08)
    with pytest.raises(PostgresDeadlineExceeded):
        run_sqlite_immediate(engine,op,retry_policy=POLICY,deadline=time.monotonic()+.05)
    assert value(engine,key)==0


@pytest.mark.parametrize('kind', ['engine', 'session'])
def test_default_postgres_unit_budget_and_explicit_short_budget(engine, kind):
    """A normal PG unit may exceed SQLite admission time; explicit caps win."""
    key=counter(engine)
    factory=create_session_factory(engine)
    def write(owner):
        owner.execute(text('SELECT pg_sleep(0.35)'))
        owner.execute(text('UPDATE g2_test_counter SET value=value+1 WHERE id=:key'),{'key':key})
    if kind=='engine':
        run_sqlite_immediate(engine,write)
        with pytest.raises(PostgresDeadlineExceeded):
            run_sqlite_immediate(engine,write,retry_policy=SqliteRetryPolicy(maximum_elapsed_seconds=.1))
    else:
        with factory() as session:
            run_sqlite_session_immediate(session,lambda:write(session))
            with pytest.raises(PostgresDeadlineExceeded):
                run_sqlite_session_immediate(session,lambda:write(session),retry_policy=SqliteRetryPolicy(maximum_elapsed_seconds=.1))
    assert value(engine,key)==1

def test_read_snapshot_detection_preserves_already_flushed_core_write(engine):
    factory=create_session_factory(engine)
    with factory() as s:
        s.scalar(select(User).where(User.id=='social-uow-owner'))
        require_read_only_session(s,error_code='dirty')
        s.execute(text('UPDATE users SET display_name=display_name WHERE id=:id'),{'id':'social-uow-owner'})
        with pytest.raises(RuntimeError,match='dirty'):require_read_only_session(s,error_code='dirty')
        s.rollback()

def test_serialization_retry_keeps_both_increment_transactions(engine):
    key=counter(engine);barrier=Barrier(2)
    def worker(_):
        attempts=[]
        def op(c):
            n=c.execute(text('SELECT value FROM g2_test_counter WHERE id=:key'),{'key':key}).scalar_one()
            attempts.append(1)
            if len(attempts)==1:barrier.wait(timeout=5)
            c.execute(text('UPDATE g2_test_counter SET value=:n WHERE id=:key'),{'n':n+1,'key':key})
        run_sqlite_immediate(engine,op,retry_policy=POLICY)
        return len(attempts)
    with ThreadPoolExecutor(2) as pool:attempts=list(pool.map(worker,[0,1]))
    assert value(engine,key)==2 and max(attempts)>1

def test_pg_query_cancel_returns_connection_clean(engine):
    with engine.connect() as c:
        start=time.monotonic()
        with pytest.raises(TimeoutError,match='canonical_read_deadline'):
            with read_deadline(c,time.monotonic()+.1):c.execute(text('SELECT pg_sleep(3)'))
        c.rollback()
        assert time.monotonic()-start<2
        assert c.execute(text('SELECT 1')).scalar_one()==1

def test_owner_and_autonomous_posts_commit_and_replay_once(engine):
    factory=create_session_factory(engine);key=uuid.uuid4().hex;barrier=Barrier(2)
    commands=[replace(_owner_post(),idempotency_key='pg-owner-'+key),replace(_autonomous_post(),idempotency_key='pg-agent-'+key)]
    def write(i):
        with factory() as s:
            u=SqlAlchemySocialWriteUnitOfWork(s)
            barrier.wait(timeout=5)
            return (u.create_owner_post if i==0 else u.apply_validated_autonomous_result)(commands[i])
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(write,[0,1]))
    assert len({r.post.id for r in results})==2
    for i in range(2):
        with factory() as s:
            u=SqlAlchemySocialWriteUnitOfWork(s,retry_policy=POLICY)
            replay=(u.create_owner_post if i==0 else u.apply_validated_autonomous_result)(commands[i])
            assert replay.replayed and replay.post.id==results[i].post.id
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Post).where(Post.id.in_([r.post.id for r in results])))==2

def test_social_partial_write_fault_rolls_back_all_rows(engine):
    factory=create_session_factory(engine);key=uuid.uuid4().hex
    with factory() as s:before=s.scalar(select(func.count()).select_from(Post))
    def fail(stage):raise RuntimeError('injected_'+stage)
    with factory() as s,pytest.raises(RuntimeError,match='injected_'):
        SqlAlchemySocialWriteUnitOfWork(s,retry_policy=POLICY,failure_injector=fail).create_owner_post(replace(_owner_post(),idempotency_key=key))
    with factory() as s:assert s.scalar(select(func.count()).select_from(Post))==before

def test_json_types_scope_and_constraints(engine):
    with engine.connect() as c:
        assert c.execute(text("SELECT json_extract('{\"a\":{\"b\":\"메이\"}}'::jsonb,'$.a.b')")).scalar_one()=='메이'
        assert c.execute(text("SELECT json_valid('invalid')")).scalar_one()==0
        assert c.execute(text("SELECT json_type('{\"a\":\"x\"}','$.a')")).scalar_one()=='text'
    factory=create_session_factory(engine)
    with factory() as s:
        s.add(World(id='pg-bad-'+uuid.uuid4().hex,slug=uuid.uuid4().hex,owner_user_id='not-a-user',name='invalid',contract_version='world-v1',contract_hash='0'*64,create_idempotency_key=uuid.uuid4().hex))
        with pytest.raises(IntegrityError):s.flush()
        s.rollback()

def test_mutation_revisions_are_transactional(engine):
    from sqlalchemy.orm import Session
    from app.runtime.memory.vector_proof import revisions
    with Session(engine) as s:
        before=revisions(s,('world:social-uow-world',))
    with engine.begin() as c:c.execute(text("UPDATE posts SET body=body||' changed' WHERE id='social-uow-target-post'"))
    with Session(engine) as s:
        after=revisions(s,('world:social-uow-world',))
    assert after[0][1]>before[0][1]

def test_embedding_payment_budget_claim_has_one_winner_and_preserves_terminal(engine):
    from app.domains.memory.repository.vector_attempts import claim,finish
    factory=create_session_factory(engine);identifier='memory-item:'+uuid.uuid4().hex
    key=(identifier,'test-profile','test-digest','test-revision');barrier=Barrier(2)
    def worker(_):
        with factory() as s:
            barrier.wait(timeout=5)
            return run_sqlite_session_immediate(s,lambda:claim(s,[key],1000),retry_policy=POLICY,require_clean=True)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(worker,[0,1]))
    assert sum(identifier in r for r in results)==1
    with factory() as s:
        run_sqlite_session_immediate(s,lambda:finish(s,*key,True),retry_policy=POLICY,require_clean=True)
        assert run_sqlite_session_immediate(s,lambda:claim(s,[key],999999),retry_policy=POLICY,require_clean=True)==set()

def test_vector_lease_reenqueue_invalidates_previous_owner(engine):
    from app.domains.memory.repository import vector_queue as q
    factory=create_session_factory(engine);item=uuid.uuid4().hex
    with factory() as s:
        run_sqlite_session_immediate(s,lambda:q.enqueue(s,'g2',item,'social-uow-world',change=1),retry_policy=POLICY,require_clean=True)
        first=run_sqlite_session_immediate(s,lambda:q.claim(s,'g2',[item]),retry_policy=POLICY,require_clean=True)[0]
        run_sqlite_session_immediate(s,lambda:q.enqueue(s,'g2',item,'social-uow-world',change=2),retry_policy=POLICY,require_clean=True)
        assert run_sqlite_session_immediate(s,lambda:q.finish(s,first,'indexed'),retry_policy=POLICY,require_clean=True) is False
        second=run_sqlite_session_immediate(s,lambda:q.claim(s,'g2',[item]),retry_policy=POLICY,require_clean=True)[0]
        assert second.revision>first.revision and second.token!=first.token
        assert run_sqlite_session_immediate(s,lambda:q.finish(s,second,'indexed'),retry_policy=POLICY,require_clean=True)

def test_deletion_fence_rejects_late_source_and_keeps_other_world(engine):
    from app.domains.worlds.models import WorldMembership
    from app.domains.worlds.service import deletion
    from app.domains.worlds.contracts_deletion import WorldDeletionCommand
    from app.runtime.world_deletion.canonical_erasure import stop_admission
    factory=create_session_factory(engine);key=uuid.uuid4().hex;world='pg-delete-'+key
    with factory() as s:
        s.add(World(id=world,slug=world,owner_user_id='social-uow-owner',name='PG deletion',contract_version='world-v1',contract_hash='0'*64,create_idempotency_key=key))
        s.flush()
        s.add(WorldMembership(id=uuid.uuid4().hex,world_id=world,user_id='social-uow-owner',role='owner',status='active'))
        s.commit()
    with factory() as s:
        receipt=deletion.accept(s,world,'social-uow-owner',WorldDeletionCommand(expected_row_version=1,confirmed_name='PG deletion',consent=True,idempotency_key=key),stop_admission=stop_admission)
        assert receipt.state=='accepted'
    with factory() as s:
        s.add(WorldMembership(id=uuid.uuid4().hex,world_id=world,user_id='social-uow-owner',role='member',status='active'))
        with pytest.raises(IntegrityError,match='world_deleting'):s.flush()
        s.rollback()
        assert s.get(World,'social-uow-world').name=='Social UoW World'

def test_relationship_settlement_and_replay_keep_exactly_one_receipt(engine):
    from datetime import UTC,datetime,timedelta
    from p7_graph_support import seed_projection_fixture
    from app.domains.relationships.service.policy_activation import activate_policy
    from runtime.test_activity_settlement_sqlite import _stage
    from app.runtime.relationships.experience_metrics import apply_pending_metrics
    from app.domains.relationships.models.personalization import RelationshipExperienceReceipt,RelationshipMetricApplication
    factory=create_session_factory(engine)
    with factory() as s:
        fixture=seed_projection_fixture(s,suffix='pg-'+uuid.uuid4().hex[:8])
        activate_policy(s,world_id=fixture.world.id,now=datetime.now(UTC)-timedelta(days=1))
        s.commit()
        identity=(fixture.world.id,fixture.actor_world_character.id,fixture.target_world_character.id,fixture.root_post.id)
    assert _stage(engine,identity)==(identity[3],)
    _stage(engine,identity,decision='pg-replay')
    with factory() as s:
        apply_pending_metrics(s,world_id=identity[0]);apply_pending_metrics(s,world_id=identity[0])
        rows=list(s.scalars(select(RelationshipExperienceReceipt).where(RelationshipExperienceReceipt.world_id==identity[0])))
        assert len(rows)==1
        applied=list(s.scalars(select(RelationshipMetricApplication).where(RelationshipMetricApplication.experience_id==rows[0].id)))
        assert len(applied)==1 and applied[0].status=='applied'


def test_pool_saturation_is_classified_without_running_or_replaying_callback(engine):
    from app.core.postgresql_concurrency import PostgresPoolExhausted
    held=[engine.connect() for _ in range(4)];calls=[]
    try:
        with pytest.raises(PostgresPoolExhausted):run_sqlite_immediate(engine,lambda c:calls.append(True),retry_policy=POLICY)
        assert not calls
    finally:
        for c in held:c.close()
    assert run_sqlite_immediate(engine,lambda c:c.execute(text('SELECT 1')).scalar_one())==1


def test_actual_deadlock_abort_is_classified_and_does_not_partially_commit(engine):
    from app.core.postgresql_concurrency import retryable
    token=uuid.uuid4().hex;ids=[token+'a',token+'b'];barrier=Barrier(2)
    with engine.begin() as c:
        for key in ids:c.execute(text('INSERT INTO g2_test_counter VALUES(:id,0)'),{'id':key})
    def worker(first,second):
        try:
            with engine.begin() as c:
                c.exec_driver_sql("SET LOCAL deadlock_timeout='100ms'");c.exec_driver_sql("SET LOCAL lock_timeout='3000ms'")
                c.execute(text('UPDATE g2_test_counter SET value=value+1 WHERE id=:id'),{'id':first})
                barrier.wait(timeout=4)
                c.execute(text('UPDATE g2_test_counter SET value=value+1 WHERE id=:id'),{'id':second})
            return 'committed'
        except DBAPIError as e:
            assert retryable(e);return e.orig.sqlstate
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker,*ids),pool.submit(worker,*reversed(ids))]
        results=[f.result(timeout=8) for f in futures]
    assert sorted(results)==['40P01','committed']
    with engine.connect() as c:assert c.execute(text('SELECT sum(value) FROM g2_test_counter WHERE id IN(:a,:b)'),{'a':ids[0],'b':ids[1]}).scalar_one()==2


@pytest.mark.parametrize('initial_input', [True, False])
def test_postgresql_relationship_reference_policy_separates_content_and_access(engine, initial_input):
    from p7_graph_support import seed_projection_fixture
    from app.domains.relationships.contracts.graph_recall import GraphRecallScope,GraphRecallResult,GraphRecallStatus,GraphRecallSource
    from app.domains.relationships.contracts.social_context import CanonicalSocialContextReference,RelationshipValidationBinding,SocialContextValidationError,CURRENTNESS_REVISION,PREVIOUS_CURRENTNESS
    from app.domains.relationships.policies.graph_recall import _relationship_record
    from app.domains.relationships.policies.social_context_validation import receipt_for_snapshot
    from app.domains.relationships.service.social_context import SocialContextService
    from app.domains.relationships.service.social_context_validation import SocialContextValidationService
    from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
    with create_session_factory(engine)() as s:
        f=seed_projection_fixture(s,suffix='guard-'+uuid.uuid4().hex[:8]);s.commit()
        scope=GraphRecallScope(f.owner.id,f.world.id,f.actor_world_character.id)
        gateway=SqlAlchemyRelationshipGraphReadGateway(s)
        facts=gateway.canonical_social_context_facts(scope=scope,references=(CanonicalSocialContextReference(f.target_world_character.id,f.relationship.id),))
        record=_relationship_record(gateway._relationship_hit(f.relationship))
        snapshot=SocialContextService(lambda q:GraphRecallResult(q.operation,GraphRecallStatus.READY,GraphRecallSource.GRAPH,relationships=(record,),candidate_count=1)).prepare(scope,labels={f.target_world_character.id:facts.nodes[f.target_world_character.id].display_name})
        binding=RelationshipValidationBinding('pg-guard-run','feed',f.root_post.id,f.target_world_character.id)
        policy=CURRENTNESS_REVISION if initial_input else PREVIOUS_CURRENTNESS
        receipt=replace(receipt_for_snapshot(snapshot,scope=scope,binding=binding),revision=policy).to_dict()
        service=SocialContextValidationService(gateway)
        prompt=snapshot.prompt_view()
        values=dict(scope=scope,binding=binding,prompt=prompt,receipt=receipt,policy=policy)
        assert service.validate(**values).outcome=='valid'
        f.relationship.version+=1;s.commit()
        if not initial_input:
            with pytest.raises(SocialContextValidationError,match='version_changed'):service.validate(**values)
            return
        assert service.validate(**values).outcome=='valid'
        assert prompt==snapshot.prompt_view()
        f.target_world_character.status='inactive';s.commit()
        with pytest.raises(SocialContextValidationError,match='visibility_lost'):service.validate(**values)


def test_chat_message_ids_thread_scope_and_rollback_on_postgresql(engine):
    from p7_graph_support import seed_projection_fixture
    from app.domains.chat.models import MessageThread,MessageMessage
    from app.domains.chat.repository import threads
    with create_session_factory(engine)() as s:
        f=seed_projection_fixture(s,suffix='chat-'+uuid.uuid4().hex[:8]);s.commit()
        thread=MessageThread(id=uuid.uuid4().hex,requester_id=f.owner.id,character_id=f.actor.id,
            world_scope_status='ambiguous',model_binding_mode='thread_override',selected_model='synthetic-model')
        s.add(thread);s.flush()
        messages=[MessageMessage(thread_id=thread.id,role='user',content='합성 질문'),MessageMessage(thread_id=thread.id,role='assistant',content='합성 응답')]
        s.add_all(messages);s.commit()
        assert messages[0].id!=messages[1].id
        assert threads.get_owned_thread(s,f.owner.id,thread.id).id==thread.id
        assert threads.get_owned_thread(s,f.other_owner.id,thread.id) is None
        messages[1].content='rollback';s.flush();s.rollback()
        assert messages[1].content=='합성 응답'
