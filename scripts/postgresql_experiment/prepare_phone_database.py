"""One-time empty target preparation used by G4; never replaces an existing DB.

Run only in the already owned/prepared G1 trial. The successful original run is
recorded as phone-g4-target-prepared.json. Migration and serving are separate.
"""
import json,os,urllib.parse
import phone_app,phone_pg
from guard import RUN_ID,SOURCE_SHA,owned_path,write_private_once


def prepare():
    root=phone_pg.root()
    if owned_path(root,'secrets/app-dsn').exists():raise ValueError('migration_target_already_prepared')
    phone_app.start('postgres')
    result=phone_pg.sql("SELECT 1 FROM pg_database WHERE datname='angmoo_pg_run01'")
    if result['returncode'] or result['stdout'].strip():raise ValueError('migration_target_not_empty')
    result=phone_pg.sql('CREATE DATABASE angmoo_pg_run01')
    if result['returncode']:raise ValueError('migration_target_create_failed')
    result=phone_pg.sql("CREATE EXTENSION vector; CREATE EXTENSION pg_trgm; CREATE TABLE angmoo_experiment_identity(singleton boolean PRIMARY KEY CHECK(singleton),run_id text NOT NULL,source_sha text NOT NULL); INSERT INTO angmoo_experiment_identity VALUES(true,'"+RUN_ID+"','"+SOURCE_SHA+"');",db='angmoo_pg_run01')
    if result['returncode']:raise ValueError('migration_target_schema_prepare_failed')
    password=owned_path(root,'secrets/password').read_text().strip()
    dsn='postgresql+psycopg://'+phone_pg.ROLE+':'+urllib.parse.quote(password,safe='')+'@127.0.0.1:15414/angmoo_pg_run01'
    path=owned_path(root,'secrets/app-dsn')
    write_private_once(path,dsn+'\n')
    return {'state':'TARGET_STAGED','extensions':['vector','pg_trgm'],'database':'angmoo_pg_run01'}


if __name__=='__main__':
    os.umask(0o077)
    try:print(json.dumps(prepare()))
    except ValueError as exc:
        print(json.dumps({'state':'FAILED','reason':str(exc)}));raise SystemExit(2) from None
