"""Create the explicit, disposable compatibility fixture used by PG contracts."""
import os
import psycopg
from sqlalchemy.engine import make_url


def main():
    dsn=os.environ['ANGMOO_EXPERIMENT_DATABASE_URL']
    url=make_url(dsn)
    if (url.host,url.port,url.database,url.username)!=('127.0.0.1',15414,'angmoo_pg_run01','angmoo_pg_run01_admin'):
        raise ValueError('ci_postgresql_fixture_identity_invalid')
    with psycopg.connect(dsn.replace('postgresql+psycopg://','postgresql://'),autocommit=True) as db:
        if db.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]:
            raise ValueError('ci_postgresql_fixture_requires_empty_database')
        db.execute('CREATE EXTENSION vector');db.execute('CREATE EXTENSION pg_trgm')
        db.execute('CREATE TABLE angmoo_experiment_identity(singleton boolean PRIMARY KEY,run_id text,source_sha text)')
        from app.runtime.postgresql_experiment import RUN_ID,SOURCE_SHA
        db.execute('INSERT INTO angmoo_experiment_identity VALUES(true,%s,%s)',(RUN_ID,SOURCE_SHA))
    print('Disposable PostgreSQL compatibility fixture prepared; no user source selected.')


if __name__=='__main__':main()
