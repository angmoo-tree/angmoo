"""Shared installation, offline migration and credentials for all local platforms.

DSNs are read from private files, never returned in support records. Platform
launchers own stopping the source and selecting the verified installation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.database import create_database_engine
from app.runtime.persistence import postgresql_identity as identity
from app.runtime.postgresql_migration import Migration, files, file_hash, inspect_source

RULES_VERSION = 1


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temporary, path)


def private_file(path, body):
    from app.core.secret_file_access import create_secret_once, protect_existing_secret
    if path.exists():
        protect_existing_secret(path, protect_parent=True)
        if path.read_bytes() != body:
            raise ValueError('postgresql_existing_secret_mismatch')
    else:
        create_secret_once(path, body)


def read_dsn(path):
    from app.core.secret_file_access import protect_existing_secret
    path = Path(path)
    protect_existing_secret(path, protect_parent=False)
    value = path.read_text(encoding='utf-8').strip()
    url = make_url(value)
    if url.get_backend_name() != 'postgresql' or not url.host or not url.username or not url.password or not url.database:
        raise ValueError('postgresql_dsn_invalid')
    return url.set(drivername='postgresql+psycopg').render_as_string(hide_password=False)


def prepare_target(dsn, installation_id):
    engine = create_database_engine(dsn)
    try:
        with engine.begin() as c:
            present = set(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).scalars())
            if present:
                if identity.IDENTITY_TABLE not in present:
                    raise ValueError('postgresql_target_not_empty')
                identity.verify(c, installation_id)
            else:
                identity.create(c, installation_id)
            c.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS vector')
            c.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    finally:
        engine.dispose()


def snapshot(source, work, installation_id):
    source, work = Path(source).absolute(), Path(work).absolute()
    identity.require_identifier(installation_id)
    if source == work or source in work.parents or work in source.parents:
        raise ValueError('migration_source_work_overlap')
    if any(p.is_symlink() or p.is_junction() for p in (source,work,*source.parents,*work.parents)):
        raise ValueError('migration_source_link_refused')
    rows = files(source)
    required=sum(row['size'] for row in rows)*2+256*1024**2
    ancestor=work.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<required:raise ValueError('migration_snapshot_space_low')
    digest = hashlib.sha256(json.dumps(rows,separators=(',',':'),sort_keys=True).encode()).hexdigest()
    marker = work/'snapshot.json'
    if marker.exists():
        manifest = json.loads(marker.read_text(encoding='utf-8'))
        if manifest.get('snapshot_digest') != digest or manifest.get('installation_id') != installation_id:
            raise ValueError('migration_snapshot_resume_mismatch')
    else:
        if work.exists() and any(work.iterdir()):
            raise ValueError('migration_work_not_empty')
        from app.runtime.persistence.postgresql_schema import VERSION
        from app.runtime.product_identity import runtime_identity
        manifest = {'schema':'angmoo-migration-snapshot.v1','installation_id':installation_id,
            'source_version':'0.1.3','target_version':'0.1.4','target_schema':VERSION,
            'target_source_sha':runtime_identity()['source_sha'],
            'rules_version':RULES_VERSION,'migration_id':uuid4().hex,'snapshot_digest':digest,'files':rows}
        write_json(marker, manifest)
    for directory in ('D0','D1'):
        for row in rows:
            target = work/directory/row['path']
            if target.exists():
                if not target.is_file() or target.stat().st_size != row['size'] or file_hash(target) != row['sha256']:
                    raise ValueError('migration_partial_snapshot_changed')
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source/row['path'],target)
            if file_hash(target) != row['sha256']:
                raise ValueError('migration_source_changed_during_backup')
    if files(source) != rows:
        raise ValueError('migration_source_changed_during_backup')
    # Old serving leases are never live ownership in the new installation;
    # the converter records them only as historical recovery evidence.
    result=inspect_source(work/'D1')
    write_json(work/'source-inspection.json',result)
    return manifest


def provision_runtime(owner_dsn, runtime_dsn, installation_id):
    from app.core.postgresql_capacity import RUNTIME_CONNECTION_LIMIT
    runtime = make_url(runtime_dsn)
    owner = make_url(owner_dsn)
    if (runtime.host,runtime.port,runtime.database) != (owner.host,owner.port,owner.database) or runtime.username == owner.username:
        raise ValueError('postgresql_runtime_role_separation_required')
    if len(runtime.password or '') < 32:
        raise ValueError('postgresql_runtime_password_invalid')
    with psycopg.connect(owner_dsn.replace('postgresql+psycopg://','postgresql://',1)) as db:
        row=db.execute('SELECT installation_id,product,contract FROM angmoo_postgresql_installation WHERE singleton').fetchone()
        if row != (installation_id,'angmoo',1):
            raise ValueError('postgresql_installation_identity_mismatch')
        role=db.execute("SELECT shobj_description(oid,'pg_authid'),rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s",(runtime.username,)).fetchone()
        if role is None:
            db.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT {} PASSWORD {}').format(sql.Identifier(runtime.username),sql.Literal(RUNTIME_CONNECTION_LIMIT),sql.Literal(runtime.password)))
            db.execute(sql.SQL('COMMENT ON ROLE {} IS {}').format(sql.Identifier(runtime.username),sql.Literal(installation_id)))
        elif role[0] != installation_id or any(role[1:]):
            raise ValueError('postgresql_runtime_role_owner_mismatch')
        else:
            db.execute(sql.SQL('ALTER ROLE {} CONNECTION LIMIT {} PASSWORD {}').format(sql.Identifier(runtime.username),sql.Literal(RUNTIME_CONNECTION_LIMIT),sql.Literal(runtime.password)))
        db.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(owner.database)))
        db.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(owner.database),sql.Identifier(runtime.username)))
        db.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        db.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(runtime.username)))
        db.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(runtime.username)))
        db.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(sql.Identifier(runtime.username)))
        for table in ('angmoo_postgresql_installation','angmoo_postgresql_schema_version','checkpoint_migrations','pg_checkpoint_contract','pg_migration_state','pg_migration_tables','pg_migration_checkpoints'):
            if db.execute('SELECT to_regclass(%s)',(table,)).fetchone()[0]:
                db.execute(sql.SQL('REVOKE INSERT,UPDATE,DELETE ON {} FROM {}').format(sql.Identifier(table),sql.Identifier(runtime.username)))


def bind_runtime(data_root, installation_id, runtime_dsn):
    root=Path(data_root)
    private_file(root/'secrets/postgresql-runtime-dsn', (runtime_dsn+'\n').encode())
    marker=root/'runtime/postgresql-runtime.json'
    previous=json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else {}
    write_json(marker,{**previous,'schema':'angmoo-postgresql-runtime.v1','installation_id':installation_id,'dsn_file':'secrets/postgresql-runtime-dsn'})


def migrate(work, owner_dsn, runtime_dsn, data_root):
    work=Path(work)
    manifest=json.loads((work/'snapshot.json').read_text(encoding='utf-8'))
    installation_id=manifest['installation_id']
    prepare_target(owner_dsn,installation_id)
    migration=Migration(work,owner_dsn,installation_id=installation_id)
    try:
        result=migration.convert()
        migration.prepare_appdata(data_root)
        provision_runtime(owner_dsn,runtime_dsn,installation_id)
        bind_runtime(data_root,installation_id,runtime_dsn)
        write_json(work/'activation-ready.json',{'installation_id':installation_id,'data_root':str(Path(data_root).absolute()),'state':'ready_for_explicit_selection'})
        return result
    finally:
        migration.engine.dispose()


def initialize(data_root, owner_dsn, runtime_dsn, installation_id):
    from app.runtime.persistence.postgresql_schema import initialize as initialize_schema
    from app.runtime.autonomous_activity.postgresql_checkpoints import initialize as initialize_checkpoints
    root=Path(data_root)
    if (root/'canonical').exists() and any((root/'canonical').rglob('*.sqlite*')):
        raise ValueError('sqlite_data_requires_migration')
    prepare_target(owner_dsn,installation_id)
    engine=create_database_engine(owner_dsn)
    try:
        with engine.begin() as c:initialize_schema(c)
        initialize_checkpoints(owner_dsn.replace('postgresql+psycopg://','postgresql://',1))
        from app.runtime.memory.postgresql_vector import PostgresMemoryVectorIndex
        from app.runtime.memory.postgresql_generations import initialize_state
        PostgresMemoryVectorIndex(engine,generation='v1').open()
        initialize_state(engine,budget_state='fresh')
    finally:
        engine.dispose()
    root.mkdir(parents=True,exist_ok=True)
    from secrets import token_urlsafe
    secret=root/'secrets/app-secret'
    if not secret.exists():private_file(secret,(token_urlsafe(48)+'\n').encode())
    provision_runtime(owner_dsn,runtime_dsn,installation_id)
    bind_runtime(root,installation_id,runtime_dsn)
    return {'state':'initialized','installation_id':installation_id}


def main():
    parser=argparse.ArgumentParser(description='Angmoo PostgreSQL installation / PostgreSQL 설치·데이터 이전')
    parser.add_argument('action',choices=('snapshot','migrate','initialize'))
    parser.add_argument('--source-root',type=Path)
    parser.add_argument('--work',type=Path)
    parser.add_argument('--data-root',type=Path)
    parser.add_argument('--installation-id')
    parser.add_argument('--owner-dsn-file',type=Path)
    parser.add_argument('--runtime-dsn-file',type=Path)
    args=parser.parse_args()
    if args.action=='snapshot':
        if not all((args.source_root,args.work,args.installation_id)):parser.error('source-root, work and installation-id required')
        result=snapshot(args.source_root,args.work,args.installation_id)
        result={k:result[k] for k in ('schema','migration_id','snapshot_digest')}
    else:
        if not all((args.data_root,args.owner_dsn_file,args.runtime_dsn_file)):parser.error('data-root and private DSN files required')
        if args.action=='migrate' and not args.work:parser.error('work required')
        if args.action=='initialize' and not args.installation_id:parser.error('installation-id required')
        owner,runtime=read_dsn(args.owner_dsn_file),read_dsn(args.runtime_dsn_file)
        result=migrate(args.work,owner,runtime,args.data_root) if args.action=='migrate' else initialize(args.data_root,owner,runtime,args.installation_id)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    import re
    import sys
    try:main()
    except Exception as exc:
        # Driver errors can embed user rows or credentials. The public CLI
        # reports only known codes, never a raw driver traceback.
        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r'(?:migration|postgresql|sqlite)_[a-z0-9_]+',str(exc)) else type(exc).__name__
        print(json.dumps({'state':'FAILED','code':code}),file=sys.stderr)
        raise SystemExit(2) from None
