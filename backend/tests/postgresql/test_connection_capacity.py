"""Exercise the new pool's real admission/overflow release and role preservation."""
import os
import time
import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import TimeoutError
from app.database import create_database_engine
from app.core.postgresql_capacity import RUNTIME_CONNECTION_LIMIT
from app.runtime.persistence.postgresql_privileges import update_runtime_connection_limit, RUNTIME_ROLE


def isolated_dsn():
    dsn=os.environ.get('ANGMOO_EXPERIMENT_DATABASE_URL')
    if not dsn:pytest.skip('explicit isolated PostgreSQL DSN required')
    url=make_url(dsn)
    assert (url.host,url.port,url.database,url.username)==('127.0.0.1',15414,'angmoo_pg_run01','angmoo_pg_run01_admin')
    return dsn


def test_fifteen_admissions_sixteenth_bounded_then_only_ten_retained():
    engine=create_database_engine(isolated_dsn());created=[];closed=[];held=[]
    event.listen(engine,'connect',lambda *a:created.append(1))
    event.listen(engine,'close',lambda *a:closed.append(1))
    try:
        assert created==[]  # Lazy creation, not fifteen permanent backends.
        for _ in range(15):held.append(engine.connect())
        assert len({c.execute(text('SELECT pg_backend_pid()')).scalar_one() for c in held})==15
        started=time.monotonic()
        with pytest.raises(TimeoutError):engine.connect()
        assert .20<=time.monotonic()-started<1.5
        for connection in held:connection.close()
        held.clear()
        assert engine.pool.checkedout()==0 and engine.pool.checkedin()==10
        assert len(created)==15 and len(closed)==5
        with engine.connect() as connection:
            assert connection.execute(text('SELECT 1')).scalar_one()==1
        assert len(created)==15
    finally:
        for connection in held:connection.close()
        engine.dispose()


def test_existing_role_limit_update_preserves_secret_and_privileges():
    dsn=isolated_dsn();engine=create_database_engine(dsn)
    from secrets import token_hex
    from app.runtime.persistence.postgresql_privileges import provision_runtime
    provision_runtime(dsn,token_hex(32))  # Explicit fixture; no test-order dependency.
    query=text('SELECT rolpassword,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_authid WHERE rolname=:r')
    try:
        with engine.connect() as c:before=tuple(c.execute(query,{'r':RUNTIME_ROLE}).one())
        result=update_runtime_connection_limit(dsn)
        with engine.connect() as c:
            after=tuple(c.execute(query,{'r':RUNTIME_ROLE}).one())
            limit=c.execute(text('SELECT rolconnlimit FROM pg_roles WHERE rolname=:r'),{'r':RUNTIME_ROLE}).scalar_one()
        assert before==after and limit==RUNTIME_CONNECTION_LIMIT
        assert result['password_changed'] is False and result['privileges_changed'] is False
    finally:engine.dispose()
