"""Real app startup/shutdown and HTTP contracts with all SQLite opens denied."""
import asyncio,json,os,secrets,sqlite3,time,sys
import sqlite3.dbapi2
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from postgresql.test_canonical_contracts import engine
from app.runtime.postgresql_experiment import build_config,RUN_ID,SOURCE_SHA
from app.runtime.memory.postgresql_generations import initialize_state
from app.runtime.autonomous_activity.postgresql_checkpoints import initialize


@pytest.mark.parametrize('limited_runtime',[False,True])
@pytest.mark.parametrize('validation_mode',[True,False])
def test_public_app_startup_http_and_shutdown_without_sqlite(engine,tmp_path,monkeypatch,limited_runtime,validation_mode):
    root=tmp_path/'data';(root/'runtime').mkdir(parents=True);(root/'secrets').mkdir()
    (root/'runtime/postgresql-runtime.json').write_text(json.dumps({'run_id':RUN_ID,'source_sha':SOURCE_SHA}))
    (root/'secrets/app-secret').write_text(secrets.token_hex(32))
    initialize_state(engine,budget_state='fresh')
    dsn=os.environ['ANGMOO_EXPERIMENT_DATABASE_URL']
    initialize(dsn.replace('postgresql+psycopg://','postgresql://',1))
    if limited_runtime:
        from sqlalchemy.engine import make_url
        from app.runtime.memory.postgresql_vector import PostgresMemoryVectorIndex
        from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
        from app.runtime.search.postgresql_fts import PostgresFtsSearchIndex
        from app.runtime.persistence.postgresql_privileges import provision_runtime,RUNTIME_ROLE
        PostgresMemoryVectorIndex(engine).open()
        PostgresMemoryRecallIndex(engine).open()
        PostgresFtsSearchIndex(engine).open()
        password=secrets.token_urlsafe(32);provision_runtime(dsn,password)
        dsn=make_url(dsn).set(username=RUNTIME_ROLE,password=password).render_as_string(hide_password=False)
    attempts=[]
    def forbidden(*a,**k):
        attempts.append(True);raise AssertionError('PostgreSQL serving runtime opened SQLite')
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    monkeypatch.setattr(sqlite3.dbapi2,'connect',forbidden)
    from app.main import create_public_app
    from app.runtime.configuration import initialize_local_installation_identity
    app=create_public_app(runtime_config=build_config(root,dsn,validation_mode=validation_mode))
    composition=app.state.runtime_composition
    initialize_local_installation_identity(composition.session_factory)
    with TestClient(app,backend_options={'loop_factory':asyncio.SelectorEventLoop} if sys.platform=='win32' else {}) as client:
        response=client.get('/health')
        assert response.status_code==200
        assert response.json()['validation_mode'] is validation_mode
        assert response.json()['automatic_activity']==('suspended' if validation_mode else 'enabled')
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if composition.memory_recall_projection.is_caught_up:break
            time.sleep(.1)
        assert composition.memory_recall_projection.is_caught_up
        assert composition.memory_hybrid_runtime.status=='ready'
        assert composition.memory_recall_projection.index.doctor().healthy
        with composition.session_factory() as session:
            assert session.execute(text('SELECT count(*) FROM worlds')).scalar_one()>0
        # Exercise the actual owner status route and response model, not only
        # /health. The former rejected EXPERIMENT_POSTGRESQL after migration.
        from app.domains.identity.models import InstallationIdentity, User
        from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
        from app.domains.runtime.dependencies import get_current_user
        from app.runtime.diagnostics.status_composition import create_runtime_status_reader
        with composition.session_factory() as session:
            identity=session.get(InstallationIdentity,LOCAL_INSTALLATION_KEY)
            previous=(identity.bootstrap_state,identity.owner_user_id)
            identity.bootstrap_state='claimed';identity.owner_user_id='social-uow-owner'
            session.commit()
            owner=session.get(User,'social-uow-owner')
            session.expunge(owner)
        app.dependency_overrides[get_current_user]=lambda:owner
        # The HTTP result includes live in-process component observations. A
        # separate raw database probe is neither the same snapshot nor that
        # overlaid status (e.g. a recovering projector can degrade the app).
        import app.domains.runtime.router as status_router
        rendered_status=[]
        original_render=status_router.runtime_status_read
        def capture_render(value, **kwargs):
            rendered_status.append(value)
            return original_render(value, **kwargs)
        monkeypatch.setattr(status_router,'runtime_status_read',capture_render)
        try:
            response=client.get('/api/v1/runtime/status',headers={
                'Origin':'http://127.0.0.1:13114',
                'X-Angmoo-Frontend-Origin':'http://127.0.0.1:13114'})
            assert response.status_code==200,response.text
            payload=response.json()
            assert payload['runtime_profile']=='EXPERIMENT_POSTGRESQL'
            assert payload['persistence_provider']=='postgresql'
            assert payload['migration']['state']=='ready'
            assert 'sqlite' not in {c['name'] for c in payload['components']}
            pg=next(c for c in payload['components'] if c['name']=='postgresql')
            backend=next(c for c in payload['components'] if c['name']=='backend')
            assert pg['state']=='ready'
            assert backend['dependencies'][0]['name']=='postgresql'
            with composition.session_factory() as session:
                actual=create_runtime_status_reader(session,config=app.state.runtime_settings).read_status()
            assert len(rendered_status)==1
            assert payload['installation_state']==rendered_status[0].installation_state
            assert actual.persistence_provider=='postgresql'
        finally:
            app.dependency_overrides.pop(get_current_user)
            with composition.session_factory() as session:
                identity=session.get(InstallationIdentity,LOCAL_INSTALLATION_KEY)
                identity.bootstrap_state,identity.owner_user_id=previous
                session.commit()
        if limited_runtime:
            from sqlalchemy.exc import DBAPIError
            for statement in ('CREATE TABLE forbidden_runtime_ddl(id int)',
                    'UPDATE angmoo_postgresql_schema_version SET version=version'):
                with pytest.raises(DBAPIError) as raised:
                    with composition.engine.begin() as connection:connection.execute(text(statement))
                assert raised.value.orig.sqlstate=='42501'
        assert not attempts
    assert not attempts
    assert composition.checkpoint_store._pool is None
    assert not tuple(root.rglob('*.sqlite*'))
