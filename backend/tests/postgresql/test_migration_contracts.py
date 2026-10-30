import hashlib,json,os,shutil,sqlite3,uuid
from pathlib import Path
import psycopg
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
import pytest
from app.runtime.postgresql_migration import Migration,files,inspect_source
from app.runtime.persistence.postgresql_schema import metadata
from app.runtime.postgresql_experiment import RUN_ID,SOURCE_SHA
from social.test_l4_social_write_uow import _seed
from app.database import create_session_factory


def test_reviewed_checkpoint_enum_roundtrip():
    from app.runtime.postgresql_migration_checkpoints import StrictReader
    from app.domains.memory.contracts.hybrid_recall import RecallAxisStatus
    reader=StrictReader();value={'receipt':{'status':RecallAxisStatus.READY}}
    kind,payload=reader.serde.dumps_typed(value)
    loaded=reader.load(kind,payload)
    assert loaded==value and isinstance(loaded['receipt']['status'],RecallAxisStatus)


def test_unknown_and_corrupt_schema_refused(tmp_path):
    p=tmp_path/'canonical/generations/test/angmoo.sqlite3';p.parent.mkdir(parents=True)
    with sqlite3.connect(p) as c:
        c.execute('CREATE TABLE angmoo_schema_version(schema_version,source_revision,source_migration_count)')
        c.execute("INSERT INTO angmoo_schema_version VALUES(42,'future',118)")
    with pytest.raises(ValueError,match='migration_source_schema_unsupported'):inspect_source(tmp_path)
    p.write_bytes(b'not-a-database')
    with pytest.raises(ValueError,match='migration_source_schema_unknown'):inspect_source(tmp_path)


def test_working_source_allows_only_empty_wal_recreation(tmp_path):
    source=tmp_path/'D1';source.mkdir()
    database=source/'fixture.sqlite';database.write_bytes(b'unchanged database')
    migration=object.__new__(Migration)
    migration.source=source;migration.manifest={'files':files(source)}
    wal=source/'fixture.sqlite-wal';wal.write_bytes(b'')
    migration.verify_working_source()
    wal.write_bytes(b'changed WAL frames')
    with pytest.raises(ValueError,match='migration_working_source_changed'):
        migration.verify_working_source()
    migration.manifest={'files':files(source)}
    wal.write_bytes(b'')
    with pytest.raises(ValueError,match='migration_working_source_changed'):
        migration.verify_working_source()


def test_all_canonical_types_resume_and_source_preservation(tmp_path):
    dsn=os.environ.get('ANGMOO_EXPERIMENT_DATABASE_URL')
    if not dsn:pytest.skip('explicit local experiment PostgreSQL required')
    source=tmp_path/'D0';canonical=source/'canonical/generations/contributor-v1/angmoo.sqlite3';canonical.parent.mkdir(parents=True)
    e=create_engine('sqlite+pysqlite:///'+canonical.as_posix())
    metadata()  # Register the current models, then create the frozen SQLite 41 input.
    from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata
    build_sqlite_baseline_metadata().create_all(e)
    with e.begin() as c:
        c.execute(text('CREATE TABLE angmoo_schema_version(schema_version integer,source_revision text,source_migration_count integer)'))
        c.execute(text("INSERT INTO angmoo_schema_version VALUES(41,'20261022_0118',117)"))
    _seed(create_session_factory(e));e.dispose()
    before=files(source);shutil.copytree(source,tmp_path/'D1')
    snapshot=hashlib.sha256(json.dumps(before,separators=(',',':'),sort_keys=True).encode()).hexdigest()
    (tmp_path/'snapshot.json').write_text(json.dumps({'run_id':RUN_ID,'source_sha':SOURCE_SHA,'snapshot_digest':snapshot,'files':before,'migration_id':'synthetic-'+uuid.uuid4().hex}))
    url=make_url(dsn);assert url.host=='127.0.0.1' and url.port==15414 and url.database=='angmoo_pg_run01'
    name='angmoo_pg_run01_g4test_'+uuid.uuid4().hex[:10]
    with psycopg.connect(dsn.replace('postgresql+psycopg://','postgresql://',1),autocommit=True) as pg:
        pg.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(name)))
    target=url.set(database=name).render_as_string(hide_password=False)
    with psycopg.connect(target.replace('postgresql+psycopg://','postgresql://',1)) as pg:
        pg.execute('CREATE EXTENSION vector');pg.execute('CREATE EXTENSION pg_trgm')
        pg.execute('CREATE TABLE angmoo_experiment_identity(singleton boolean PRIMARY KEY,run_id text,source_sha text)')
        pg.execute('INSERT INTO angmoo_experiment_identity VALUES(true,%s,%s)',(RUN_ID,SOURCE_SHA))
    m=Migration(tmp_path,target)
    try:
        assert m.convert(stop_after='canonical')['state']=='interrupted_after_canonical'
        assert m.verify_canonical()
        assert m.convert(stop_after='vectors')['state']=='interrupted_after_vectors'
        assert m.convert(stop_after='checkpoints')['state']=='interrupted_after_checkpoints'
        m.mark('aborted')
        result=m.convert()
        assert result['state']=='VERIFIED' and result['tables']==181
        assert result['vectors']['new_embedding_calls']==0
        assert m.convert()['state']=='VERIFIED'
        assert files(source)==before
        modified=tmp_path/'D1/canonical/generations/contributor-v1/angmoo.sqlite3'
        original=modified.read_bytes()
        with sqlite3.connect(modified) as c:c.execute("UPDATE users SET display_name='changed working copy'")
        with pytest.raises(ValueError,match='migration_working_source_changed'):m.prepare()
        modified.write_bytes(original)
        # An unrelated migration identity may not resume into this database.
        value=json.loads((tmp_path/'snapshot.json').read_text());value['migration_id']='different'
        (tmp_path/'snapshot.json').write_text(json.dumps(value))
        other=Migration(tmp_path,target)
        try:
            with pytest.raises(ValueError,match='migration_resume_identity_mismatch'):other.prepare()
        finally:other.engine.dispose()
    finally:m.engine.dispose()
