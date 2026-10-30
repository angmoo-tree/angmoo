"""Offline schema 1/2 -> 3 upgrade of an explicitly named experiment clone."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session
from app.runtime.persistence.postgresql_schema import initialize, metadata
from app.runtime.persistence.experience_report import audit
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.domains.memory.models.items import MemoryItem


def summary_identity(db):
    digest=sha256();count=0
    for row in db.execute(select(MemoryItem.id,MemoryItem.summary,MemoryItem.version,MemoryItem.status)
            .order_by(MemoryItem.id).execution_options(yield_per=100)):
        digest.update(json.dumps(list(row),ensure_ascii=False).encode());digest.update(b'\n');count+=1
    return {'rows':count,'sha256':digest.hexdigest()}


def upgrade(dsn, *, expected_database):
    parsed=urlsplit(dsn)
    if (not re.fullmatch(r'angmoo_pg_run01_(restore|snapshot_[a-z0-9_]+)',expected_database)
            or parsed.hostname!='127.0.0.1' or parsed.port!=15414
            or parsed.path!='/'+expected_database or parsed.username!='angmoo_pg_run01_admin'):
        raise ValueError('snapshot_upgrade_requires_owned_clone')
    if parsed.scheme not in {'postgresql','postgresql+psycopg'}:
        raise ValueError('snapshot_upgrade_dsn_invalid')
    engine=create_engine(dsn.replace('postgresql://','postgresql+psycopg://',1),pool_size=1,max_overflow=0)
    try:
        with engine.begin() as connection:
            identity=connection.execute(text('SELECT run_id,source_sha FROM angmoo_experiment_identity WHERE singleton=true')).one()
            if tuple(identity)!=('angmoo-pg-20261027-run01','b1287c9be6b1480858f86a1235aea9730ff59468'):
                raise ValueError('snapshot_upgrade_identity_mismatch')
            clients=connection.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND usename='angmoo_pg_run01_runtime'")).scalar_one()
            if clients:raise ValueError('snapshot_upgrade_application_must_be_stopped')
            connection.execute(text('SELECT pg_advisory_xact_lock(7402228)'))
            metadata()  # Register all ORM targets before reading an older schema.
            with Session(bind=connection,join_transaction_mode="create_savepoint") as db:before=summary_identity(db)
            initialize(connection, experience_sources=lambda session: RuntimeEpisodeDetailReader(session).read_sources)
            with Session(bind=connection,join_transaction_mode="create_savepoint") as db:
                after=summary_identity(db);report=audit(db)
            if before!=after or not report['valid']:
                raise ValueError('snapshot_upgrade_verification_failed')
        return {'state':'VERIFIED','database':expected_database,'schema_version':3,
            'summary_preserved':before==after,'experience_snapshots':report}
    finally:engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--dsn-file',type=Path,required=True)
    parser.add_argument('--expected-database',required=True)
    args=parser.parse_args()
    try:result=upgrade(args.dsn_file.read_text().strip(),expected_database=args.expected_database)
    except Exception as exc:
        safe=str(exc) if isinstance(exc,ValueError) and str(exc).startswith('snapshot_upgrade_') else type(exc).__name__
        print(json.dumps({'state':'FAILED','code':safe}));raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=False))
