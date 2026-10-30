"""Development probe against the specifically owned local DB; no drops."""
import json,pathlib,sys
from sqlalchemy import URL,inspect,text
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.database import create_database_engine
from app.runtime.persistence.postgresql_schema import initialize

def pc_engine():
    password=pathlib.Path('E:/angmoo-local/postgresql-termux-20261027/run-01/secrets/pc-postgres-password').read_text().strip()
    url=URL.create('postgresql+psycopg',username='angmoo_pg_run01_admin',password=password,
        host='127.0.0.1',port=15414,database='angmoo_pg_run01')
    engine=create_database_engine(url.render_as_string(hide_password=False))
    with engine.connect() as conn:
        assert conn.execute(text('SELECT run_id FROM angmoo_experiment_identity')).scalar_one()=='angmoo-pg-20261027-run01'
    return engine

if __name__=='__main__':
    engine=pc_engine()
    with engine.begin() as connection:
        result=initialize(connection)
        print(json.dumps({'canonical_tables':len(result.tables),'database_tables':len(inspect(connection).get_table_names())}))
