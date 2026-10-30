"""Official engine against a real, disposable PostgreSQL database."""
import os
import uuid
from pathlib import Path
import psycopg
from psycopg import sql
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from app.database import create_session_factory
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata
from app.runtime.postgresql_installation import snapshot,prepare_target,migrate
from app.runtime.postgresql_migration import Migration,files
from social.test_l4_social_write_uow import _seed


def test_official_source_conversion_resumes_and_preserves_data(tmp_path,monkeypatch):
    admin=os.environ.get('ANGMOO_TEST_ADMIN_DSN')
    if not admin:pytest.skip('explicit disposable PostgreSQL test administrator required')
    url=make_url(admin);assert url.host in {'127.0.0.1','localhost'}
    name='angmoo_test_migration_'+uuid.uuid4().hex[:16]
    target=url.set(database=name).render_as_string(hide_password=False)
    connect=lambda dsn:psycopg.connect(dsn.replace('postgresql+psycopg://','postgresql://'),autocommit=True)
    with connect(admin) as db:db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    source=tmp_path/'source';database=source/'canonical/generations/official013/angmoo.sqlite3'
    database.parent.mkdir(parents=True)
    engine=create_engine('sqlite+pysqlite:///'+database.as_posix())
    build_sqlite_baseline_metadata().create_all(engine)
    with engine.begin() as db:
        db.execute(text('CREATE TABLE angmoo_schema_version(schema_version integer,source_revision text,source_migration_count integer)'))
        db.execute(text("INSERT INTO angmoo_schema_version VALUES(41,'20261022_0118',117)"))
    _seed(create_session_factory(engine));engine.dispose()
    (source/'secrets').mkdir();(source/'secrets/app-secret').write_text('synthetic-migration-secret-'+'a'*40)
    original=files(source);work=tmp_path/'work';identifier='angmoo-'+uuid.uuid4().hex
    runtime=url.set(database=name,username='runtime_'+uuid.uuid4().hex[:12],password=uuid.uuid4().hex*2).render_as_string(hide_password=False)
    converter=None
    try:
        snapshot(source,work,identifier);prepare_target(target,identifier)
        converter=Migration(work,target,installation_id=identifier)
        assert converter.convert(stop_after='canonical')['state']=='interrupted_after_canonical'
        converter.engine.dispose();converter=None
        # A mounted Docker volume already exists as an empty directory.
        (tmp_path/'appdata').mkdir()
        result=migrate(work,target,runtime,tmp_path/'appdata')
        assert result['state']=='VERIFIED' and result['tables']==181 and result['rows']>0
        assert result['vectors']['new_embedding_calls']==0
        assert files(source)==original
        # Completed offline conversion is idempotent before activation.
        assert migrate(work,target,runtime,tmp_path/'appdata')['state']=='VERIFIED'
        with connect(runtime) as db:
            assert db.execute('SELECT count(*) FROM users').fetchone()[0]>0
            assert db.execute('SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()==(False,False,False)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):db.execute('DELETE FROM angmoo_postgresql_installation')
        import sqlite3
        import sqlite3.dbapi2
        from fastapi.testclient import TestClient
        from app.runtime.postgresql_server import create_app
        from app.domains.runtime.dependencies import get_current_user
        from app.domains.identity.models import User
        def forbidden(*_a,**_k):raise AssertionError('Official PostgreSQL serving opened SQLite')
        monkeypatch.setattr(sqlite3,'connect',forbidden);monkeypatch.setattr(sqlite3.dbapi2,'connect',forbidden)
        app=create_app(tmp_path/'appdata','http://127.0.0.1:3000',validation_mode=True)
        factory=app.state.runtime_composition.session_factory
        with factory() as session:
            owner=session.get(User,'social-uow-owner');session.expunge(owner)
        app.dependency_overrides[get_current_user]=lambda:owner
        import asyncio
        with TestClient(app,backend_options={'loop_factory':asyncio.SelectorEventLoop} if os.name=='nt' else {}) as client:
            health=client.get('/health')
            assert health.status_code==200 and health.json()['persistence']=='postgresql'
            assert health.json()['profile']=='CONTRIBUTOR_POSTGRESQL'
            status=client.get('/api/v1/runtime/status',headers={'Origin':'http://127.0.0.1:3000','X-Angmoo-Frontend-Origin':'http://127.0.0.1:3000'})
            assert status.status_code==200 and status.json()['persistence_provider']=='postgresql'
        # Exercise new recovery control columns in this converted database,
        # rather than substituting a separately initialized schema5 fixture.
        # Provider output is synthetic; no key is transmitted.
        from app.database import create_database_engine
        from sqlalchemy.orm import Session,sessionmaker
        from memory.test_maintenance_rounds import closed_fixture
        from memory.test_manual_relationship_followup import finish_memory
        from test_relationship_daily_review import Provider,References
        from app.domains.memory.service import consolidation_requests as requests
        from app.domains.relationships.models.manual_review import RelationshipReviewRequest
        from app.runtime.relationships.manual_review_worker import advance_manual_requests
        from app.domains.relationships.service.daily_review import run_review_step,apply_review
        from datetime import UTC,datetime
        from app.runtime.memory.maintenance_slot import MaintenanceSlot
        converted=create_database_engine(runtime)
        try:
            factory=sessionmaker(converted,expire_on_commit=False)
            with Session(converted,expire_on_commit=False) as db:
                scope,workflows,data,original,old,payloads,future=closed_fixture(db,monkeypatch)
                old_id=old.id;payloads.extend(future)
                result=requests.submit(scope=scope,db=db,workflows=workflows,
                    data=data.model_copy(update={'idempotency_key':uuid.uuid4().hex}))
                finish_memory(db,result['request_id']);advance_manual_requests(db,datetime.now(UTC));db.commit()
                request=db.get(RelationshipReviewRequest,result['request_id'])
                assert len(request.snapshot)==3 and old_id not in request.work_ids
                work_id=request.work_ids[0]
            # Close the reading snapshot before the provider transition, just
            # as the runtime does. A SQLite-only fixture holding one Session
            # across both transactions is not valid at SERIALIZABLE isolation.
            provider=Provider()
            assert asyncio.run(run_review_step(factory,work_id=work_id,references_factory=lambda db:References(),
                provider_factory=lambda base:provider))=='ready'
            with factory() as db:
                apply_review(db,work_id=work_id,references=References(),now=datetime.now(UTC))
                advance_manual_requests(db,datetime.now(UTC));db.commit()
                progress=requests.read(scope=scope,db=db,workflows=workflows)['progress']['relationship']
                assert (progress['target_count'],progress['completed_count'],progress['changed_count'])==(1,1,1)
                assert len(provider.calls)==1
            first,second=MaintenanceSlot(sessionmaker(converted)),MaintenanceSlot(sessionmaker(converted))
            token=first.acquire('memory');assert token and second.acquire('relationship') is None
            first.release(token);token=second.acquire('relationship');assert token;second.release(token)
        finally:converted.dispose()
    finally:
        if converter:converter.engine.dispose()
        with connect(admin) as db:
            db.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
            db.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(make_url(runtime).username)))
