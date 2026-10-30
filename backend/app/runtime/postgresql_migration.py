"""Offline schema-41 converter. Only D1 uses SQLite; serving never imports it.

This module never deletes a source or an existing target. Each copied stage is
transactional and bound to the immutable D0 manifest. Reports contain counts,
schema identities and digests, never credentials or conversation text.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,math,os,sqlite3,sys
from contextlib import contextmanager
from datetime import UTC,datetime,date
from pathlib import Path
import psycopg
from urllib.parse import urlsplit
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy import Boolean,DateTime,Date,JSON,Float,Integer,text
from app.database import create_database_engine
from app.runtime.persistence.postgresql_schema import metadata,initialize
from app.runtime.persistence.experience_migration import TABLES as EXPERIENCE_TABLES
from app.runtime.postgresql_experiment import RUN_ID,SOURCE_SHA

SCHEMA=41


def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


def files(root, *, exclude=()):
    result=[]
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('migration_source_link_refused')
        if p.relative_to(root).as_posix() in exclude:continue
        if p.is_file():result.append({'path':p.relative_to(root).as_posix(),'size':p.stat().st_size,'sha256':file_hash(p)})
    return result


@contextmanager
def source_db(path):
    if not path.is_file():raise ValueError('migration_source_missing')
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents)):
        raise ValueError('migration_source_link_refused')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.5)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        yield db
    finally:db.close()


def canonical_path(root):
    pointer=root/'canonical/current-generation.json'
    if pointer.exists():
        value=json.loads(pointer.read_text(encoding='utf-8'))
        generation=value.get('generation','')
        if (value.get('schema_version')!=1 or value.get('data_version')!=41
                or not __import__('re').fullmatch(r'[A-Za-z0-9_-]+',generation)
                or value.get('relative_path')!='generations/'+generation):
            raise ValueError('migration_canonical_pointer_invalid')
        candidate=root/'canonical/generations'/generation/'angmoo.sqlite3'
        if not candidate.is_file():raise ValueError('migration_canonical_generation_missing')
        return candidate
    candidates=list((root/'canonical/generations').glob('*/angmoo.sqlite3'))
    if len(candidates)!=1:raise ValueError('migration_canonical_generation_ambiguous')
    return candidates[0]


def inspect_source(root):
    with source_db(canonical_path(root)) as db:
        try:row=db.execute('SELECT schema_version,source_revision,source_migration_count FROM angmoo_schema_version').fetchone()
        except sqlite3.Error:raise ValueError('migration_source_schema_unknown') from None
        if row!=(41,'20261022_0118',117):raise ValueError('migration_source_schema_unsupported')
        if db.execute('PRAGMA integrity_check').fetchone()!=('ok',):raise ValueError('migration_source_integrity_failed')
        if db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('migration_source_foreign_key_failed')
        from app.runtime.persistence.migration_source_v013 import metadata as source_metadata
        tables=source_metadata();inventory={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if inventory!=set(tables.tables)|{'angmoo_schema_version'}:raise ValueError('migration_source_inventory_mismatch')
        counts={}
        for table in tables.tables.values():
            if table.name in EXPERIENCE_TABLES:continue
            q='"'+table.name+'"'
            if {r[1] for r in db.execute('PRAGMA table_info('+q+')')}!={c.name for c in table.columns}:
                raise ValueError('migration_source_columns_mismatch:'+table.name)
            counts[table.name]=db.execute('SELECT count(*) FROM '+q).fetchone()[0]
    cp=root/'runtime/activity/activity-checkpoints.sqlite'
    checkpoint_count=0
    if cp.exists():
        with source_db(cp) as db:
            if db.execute('PRAGMA integrity_check').fetchone()!=('ok',):raise ValueError('migration_checkpoint_integrity_failed')
            checkpoint_count=db.execute('SELECT count(*) FROM checkpoints').fetchone()[0]
    return {'supported':True,'source_schema':41,'canonical_tables':len(counts),'table_counts':counts,
        'checkpoints':checkpoint_count,'vector_files':len(list((root/'search/memory-vectors/generations').glob('*/vectors.sqlite3')))}


def converted(column,value):
    if value is None:return None
    typ=column.type
    if isinstance(typ,JSON):
        value=json.loads(value) if isinstance(value,str) else value
        validate_text(value)
        return value
    validate_text(value)
    if isinstance(typ,Boolean):
        if value not in (0,1,False,True):raise ValueError('migration_boolean_invalid')
        return bool(value)
    if isinstance(typ,DateTime):
        value=datetime.fromisoformat(value) if isinstance(value,str) else value
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if isinstance(typ,Date):return date.fromisoformat(value) if isinstance(value,str) else value
    if isinstance(typ,Float) and not math.isfinite(value):raise ValueError('migration_float_invalid')
    return bytes(value) if isinstance(value,memoryview) else value


def validate_text(value):
    if isinstance(value,str) and any(c=='\x00' or 0xD800<=ord(c)<=0xDFFF for c in value):
        raise ValueError('migration_text_unrepresentable')
    if isinstance(value,dict):
        for key,item in value.items():validate_text(key);validate_text(item)
    elif isinstance(value,(tuple,list)):
        for item in value:validate_text(item)


def source_row(table, raw):
    from app.runtime.persistence.migration_source_v013 import source_values
    values={column.name:converted(column,value) for column,value in zip(table.columns,raw,strict=True)}
    transformed=source_values(table.name,values)
    return tuple(transformed[c.name] for c in table.columns),values


def normalized(value):
    if isinstance(value,(datetime,date)):return value.isoformat()
    if isinstance(value,(bytes,memoryview)):return {'binary':base64.b64encode(value).decode()}
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [normalized(v) for v in value]
    return value


def add_digest(hasher,row):
    hasher.update(json.dumps(normalized(row),sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())
    hasher.update(b'\n')


def table_query(table):
    columns=','.join('"'+c.name+'"' for c in table.columns)
    order=','.join('"'+c.name+'"' for c in table.primary_key.columns)
    if not order:raise ValueError('migration_primary_key_required:'+table.name)
    return 'SELECT '+columns+' FROM "'+table.name+'" ORDER BY '+order


class Migration:
    def __init__(self,work,dsn,*,installation_id=None):
        uri=urlsplit(dsn)
        self.installation_id=installation_id
        if installation_id is None and (uri.scheme not in {'postgresql','postgresql+psycopg'} or uri.hostname!='127.0.0.1'
                or uri.port!=15414 or uri.username!='angmoo_pg_run01_admin'
                or not (uri.path in {'/angmoo_pg_run01','/angmoo_pg_run01_restore'} or
                    __import__('re').fullmatch(r'/angmoo_pg_run01_g4test_[0-9a-f]{10}',uri.path))):
            raise ValueError('migration_target_dsn_refused')
        candidate=Path(work).absolute()
        if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (candidate,*candidate.parents)):
            raise ValueError('migration_work_link_refused')
        self.work=candidate.resolve();self.source=self.work/'D1'
        self.manifest=json.loads((self.work/'snapshot.json').read_text())
        if installation_id is None:
            if self.manifest.get('run_id')!=RUN_ID or self.manifest.get('source_sha')!=SOURCE_SHA:raise ValueError('migration_owner_mismatch')
        elif (self.manifest.get('schema'),self.manifest.get('installation_id'),self.manifest.get('source_version'),self.manifest.get('target_version'),self.manifest.get('rules_version')) != ('angmoo-migration-snapshot.v1',installation_id,'0.1.3','0.1.4',1):
            raise ValueError('migration_owner_mismatch')
        if installation_id is not None:
            from app.runtime.persistence.postgresql_schema import VERSION
            if self.manifest.get('target_schema')!=VERSION:raise ValueError('migration_target_schema_changed')
            from app.runtime.product_identity import runtime_identity
            current_source=runtime_identity()['source_sha']
            if current_source!='unknown' and self.manifest.get('target_source_sha')!=current_source:
                raise ValueError('migration_target_source_changed')
        self.identity=self.manifest['snapshot_digest'];self.migration_id=self.manifest['migration_id']
        self.dsn=dsn.replace('postgresql+psycopg://','postgresql://',1)
        self.engine=create_database_engine(dsn)
        with self.engine.connect() as c:
            if installation_id is None:
                if tuple(c.execute(text('SELECT run_id,source_sha FROM angmoo_experiment_identity')).one())!=(RUN_ID,SOURCE_SHA):
                    raise ValueError('migration_target_identity_mismatch')
            else:
                from app.runtime.persistence.postgresql_identity import verify
                verify(c,installation_id)
        self.tables=metadata()
        from app.runtime.persistence.migration_source_v013 import metadata as source_metadata
        self.source_tables=source_metadata()

    def verify_d0(self):
        rows=files(self.work/'D0')
        if rows!=self.manifest['files']:raise ValueError('migration_snapshot_changed')
        digest=hashlib.sha256(json.dumps(rows,separators=(',',':'),sort_keys=True).encode()).hexdigest()
        if digest!=self.identity:raise ValueError('migration_snapshot_digest_mismatch')

    def verify_working_source(self):
        # Read-only WAL readers may recreate SHM and a zero-byte WAL for an
        # existing database. Only absent/empty WAL is equivalent: a nonempty
        # WAL, database, vector/checkpoint payload, media or secret must match.
        known={r['path'] for r in self.manifest['files']}
        empty_hash=hashlib.sha256(b'').hexdigest()
        def content_rows(rows):
            return [r for r in rows if not r['path'].endswith('-shm') and not (
                r['path'].endswith('-wal') and r['path'][:-4] in known
                and r['size']==0 and r['sha256']==empty_hash)]
        expected=content_rows(self.manifest['files'])
        actual=content_rows(files(self.source))
        if actual!=expected:raise ValueError('migration_working_source_changed')

    def prepare(self):
        self.verify_d0();self.verify_working_source();inspect_source(self.source)
        with self.engine.begin() as c:
            c.exec_driver_sql('''CREATE TABLE IF NOT EXISTS pg_migration_state(singleton boolean PRIMARY KEY CHECK(singleton),
                migration_id text NOT NULL,snapshot_digest text NOT NULL,phase text NOT NULL,details jsonb NOT NULL DEFAULT '{}');''')
            row=c.execute(text('SELECT migration_id,snapshot_digest FROM pg_migration_state')).first()
            if row is None:
                present=set(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).scalars())
                if present-{'angmoo_experiment_identity','angmoo_postgresql_installation','pg_migration_state'}:raise ValueError('migration_target_not_empty')
                c.execute(text("INSERT INTO pg_migration_state VALUES(true,:id,:digest,'prepared','{}')"),{'id':self.migration_id,'digest':self.identity})
            elif tuple(row)!=(self.migration_id,self.identity):raise ValueError('migration_resume_identity_mismatch')
            initialize(c,fences=False)
            c.exec_driver_sql('''CREATE TABLE IF NOT EXISTS pg_migration_tables(name text PRIMARY KEY,row_count bigint NOT NULL,digest text NOT NULL);
                CREATE TABLE IF NOT EXISTS pg_migration_checkpoints(thread_id text,checkpoint_ns text,checkpoint_id text,source_digest text NOT NULL,
                 PRIMARY KEY(thread_id,checkpoint_ns,checkpoint_id));''')

    def stage_done(self,key):
        with self.engine.connect() as c:return c.execute(text('SELECT details->:key FROM pg_migration_state'),{'key':key}).scalar_one() is True

    def mark(self,key,value=True):
        with self.engine.begin() as c:c.execute(text('UPDATE pg_migration_state SET phase=:key,details=details||CAST(:v AS jsonb)'),{'key':key,'v':json.dumps({key:value})})

    def canonical(self):
        if self.stage_done('canonical'):return
        with source_db(canonical_path(self.source)) as db,psycopg.connect(self.dsn) as pg:
            constraints=pg.execute("SELECT conrelid::regclass::text,conname FROM pg_constraint WHERE contype='f' AND connamespace='public'::regnamespace").fetchall()
            for name,constraint in constraints:
                pg.execute(sql.SQL('ALTER TABLE {} ALTER CONSTRAINT {} DEFERRABLE INITIALLY IMMEDIATE').format(sql.Identifier(name),sql.Identifier(constraint)))
            pg.execute('SET CONSTRAINTS ALL DEFERRED')
            for table in sorted(self.source_tables.tables.values(),key=lambda t:t.name):
                if pg.execute(sql.SQL('SELECT EXISTS(SELECT 1 FROM {})').format(sql.Identifier(table.name))).fetchone()[0]:
                    raise ValueError('migration_canonical_target_not_empty:'+table.name)
                digest=hashlib.sha256();count=0
                from app.runtime.persistence.migration_source_v013 import CONTROL_TABLES,additional_values
                names=[c.name for c in table.columns]+(['maintenance'] if table.name in CONTROL_TABLES else [])
                with pg.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier(table.name),sql.SQL(',').join(map(sql.Identifier,names)))) as copy:
                    for raw in db.execute(table_query(table)):
                        row,original=source_row(table,raw)
                        add_digest(digest,row);count+=1
                        payload=tuple(Jsonb(v) if isinstance(c.type,JSON) and v is not None else v for c,v in zip(table.columns,row,strict=True))
                        extra=additional_values(table.name,original)
                        copy.write_row(payload+tuple(Jsonb(extra[n]) for n in names[len(row):]))
                pg.execute('INSERT INTO pg_migration_tables VALUES(%s,%s,%s)',(table.name,count,digest.hexdigest()))
                for column in table.columns:
                    seq=pg.execute('SELECT pg_get_serial_sequence(%s,%s)',(table.name,column.name)).fetchone()[0]
                    if seq:
                        maximum=pg.execute(sql.SQL('SELECT max({}) FROM {}').format(sql.Identifier(column.name),sql.Identifier(table.name))).fetchone()[0]
                        pg.execute('SELECT setval(%s,%s,%s)',(seq,max(1,maximum or 1),maximum is not None))
            pg.execute("UPDATE pg_migration_state SET phase='canonical',details=details||'{\"canonical\":true}'::jsonb")

    def verify_canonical(self):
        from app.runtime.persistence.migration_source_v013 import CONTROL_TABLES,additional_values
        counts={}
        with source_db(canonical_path(self.source)) as db,psycopg.connect(self.dsn) as pg:
            pg.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for table in sorted(self.source_tables.tables.values(),key=lambda t:t.name):
                expected=hashlib.sha256();actual=hashlib.sha256();control_expected=hashlib.sha256();control_actual=hashlib.sha256();n=m=0
                if table.name=='memory_vector_attempts' and self.stage_done('vectors'):
                    from app.runtime.postgresql_migration_search import budget_rows
                    source_rows=budget_rows(self)
                else:source_rows=db.execute(table_query(table))
                for row in source_rows:
                    value,original=source_row(table,row)
                    add_digest(expected,value);n+=1
                    if table.name in CONTROL_TABLES:add_digest(control_expected,additional_values(table.name,original)['maintenance'])
                with pg.cursor(name='verify_'+table.name[:40]) as cursor:
                    query=table_query(table)
                    if table.name in CONTROL_TABLES:query=query.replace(' FROM ', ',"maintenance" FROM ',1)
                    cursor.itersize=128;cursor.execute(query)
                    for row in cursor:
                        if table.name in CONTROL_TABLES:
                            add_digest(control_actual,row[-1]);row=row[:-1]
                        add_digest(actual,tuple(converted(c,v) for c,v in zip(table.columns,row,strict=True)));m+=1
                if n!=m or expected.digest()!=actual.digest():raise ValueError('migration_canonical_digest_mismatch:'+table.name)
                if control_expected.digest()!=control_actual.digest():raise ValueError('migration_control_digest_mismatch:'+table.name)
                counts[table.name]={'rows':n,'digest':expected.hexdigest()}
        return counts

    def convert(self,*,stop_after=None):
        self.prepare();self.canonical()
        if stop_after=='canonical':return {'state':'interrupted_after_canonical'}
        from app.runtime.postgresql_migration_search import convert_vectors,rebuild_search
        from app.runtime.postgresql_migration_checkpoints import convert_checkpoints
        convert_vectors(self)
        if stop_after=='vectors':return {'state':'interrupted_after_vectors'}
        convert_checkpoints(self)
        if stop_after=='checkpoints':return {'state':'interrupted_after_checkpoints'}
        if not self.stage_done('experience_snapshots'):
            from sqlalchemy.orm import Session
            from app.runtime.persistence.experience_migration import migrate
            with Session(self.engine) as db:
                snapshot_counts=migrate(db)
                db.commit()
            self.mark('experience_snapshot_counts',snapshot_counts)
            self.mark('experience_snapshots')
        if not self.stage_done('fences'):
            from app.runtime.persistence.postgresql_triggers import install
            with self.engine.begin() as c:install(c,self.tables)
            self.mark('fences')
        rebuild_search(self)
        return self.verify()

    def verify(self):
        self.verify_d0();self.verify_working_source()
        from app.runtime.postgresql_migration_search import verify_vectors
        from app.runtime.postgresql_migration_checkpoints import verify_checkpoints
        result={'schema':'angmoo-pg-migration-verification.v1','snapshot_digest':self.identity,
            'canonical':self.verify_canonical(),'vectors':verify_vectors(self),'checkpoints':verify_checkpoints(self)}
        from app.runtime.persistence.migration_source_v013 import verify_target_only
        with self.engine.connect() as connection:verify_target_only(connection)
        from sqlalchemy.orm import Session
        from app.runtime.persistence.experience_report import audit
        with Session(self.engine) as db:
            result['experience_snapshots']=audit(db)
        if not result['experience_snapshots']['valid']:
            raise ValueError('migration_experience_snapshot_verification_failed')
        result['state']='VERIFIED'
        (self.work/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
        self.mark('verified')
        return {'state':'VERIFIED','tables':len(result['canonical']),'rows':sum(x['rows'] for x in result['canonical'].values()),
            'vectors':result['vectors'],'checkpoints':result['checkpoints'],
            'experience_snapshots':result['experience_snapshots']}

    def prepare_appdata(self,target):
        import shutil
        target=Path(target).absolute()
        if self.installation_id is not None and (target == self.work or target in self.work.parents or self.work in target.parents):
            raise ValueError('migration_application_target_overlap')
        if self.installation_id is None and (target.parent.resolve()!=self.work.parent or target.name not in {'appdata','appdata-restore'}):
            raise ValueError('migration_application_target_invalid')
        if any(p.is_symlink() or p.is_junction() for p in (target,*target.parents)):raise ValueError('migration_application_target_link')
        if not self.stage_done('verified'):raise ValueError('migration_activation_requires_verification')
        self.verify_d0()
        marker=target/'runtime/postgresql-runtime.json'
        if target.exists() and any(target.iterdir()):
            if not marker.is_file() or json.loads(marker.read_text()).get('snapshot_digest')!=self.identity:
                raise ValueError('migration_application_target_not_empty')
        else:
            marker.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
            marker.write_text(json.dumps({'run_id':RUN_ID,'source_sha':SOURCE_SHA,'snapshot_digest':self.identity,'migration_id':self.migration_id}))
        copied=[]
        for row in self.manifest['files']:
            relative=Path(row['path'])
            if relative.parts[0] not in {'media','secrets'}:continue
            src=self.work/'D0'/relative;dst=target/relative
            dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            if not dst.exists():shutil.copyfile(src,dst);dst.chmod(0o600)
            if file_hash(dst)!=row['sha256']:raise ValueError('migration_application_file_mismatch')
            copied.append(row)
        from app.runtime.migrations.ladybug_versions.rebuild import rebuild_projection_v3
        from app.runtime.graph_projection.sqlalchemy_outbox import SqlAlchemyProjectionReplaySource
        from app.database import create_session_factory
        graph=rebuild_projection_v3(database_root=target/'graph/ladybug',replay_source=SqlAlchemyProjectionReplaySource(create_session_factory(self.engine)))
        (target/'runtime/migration-files.json').write_text(json.dumps(copied,indent=2)+'\n')
        (target/'runtime/graph-rebuild.json').write_text(json.dumps({'worlds':len(graph),'digest':hashlib.sha256(json.dumps(graph,sort_keys=True).encode()).hexdigest()})+'\n')
        return {'state':'READY','copied_files':len(copied),'graph_worlds':len(graph),'automatic_activity':'suspended','provider_network':'disabled'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inspect','dry-run','convert','verify','resume','abort','prepare-app'])
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--dsn-file',type=Path)
    parser.add_argument('--stop-after',choices=['canonical','vectors','checkpoints']);args=parser.parse_args()
    os.umask(0o077)
    try:
        if args.action in {'inspect','dry-run'}:result=inspect_source(args.work/'D1')
        else:
            if args.dsn_file is None:raise ValueError('migration_dsn_file_required')
            migration=Migration(args.work,args.dsn_file.read_text().strip())
            try:
                if args.action in {'convert','resume'}:result=migration.convert(stop_after=args.stop_after)
                elif args.action=='verify':result=migration.verify()
                elif args.action=='prepare-app':result=migration.prepare_appdata(args.work.parent/'appdata')
                else:migration.mark('aborted');result={'state':'ABORTED','staging_preserved':True}
            finally:migration.engine.dispose()
        print(json.dumps(result,ensure_ascii=False,default=str))
    except Exception as exc:
        # SQLAlchemy/driver exceptions can carry user rows; report only typed codes.
        reason=str(exc) if isinstance(exc,ValueError) and str(exc).startswith('migration_') else type(exc).__name__
        print(json.dumps({'state':'FAILED','reason':reason}),file=sys.stderr)
        raise SystemExit(2) from None


if __name__=='__main__':main()
