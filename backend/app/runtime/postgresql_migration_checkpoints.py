"""Explicit SDK conversion with strict safe deserialization and exact write IDs."""
import hashlib,json
import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.serde.event_hooks import register_serde_event_listener
from app.runtime.persistence.sqlite_migration_io import source_db
from app.runtime.autonomous_activity.postgresql_checkpoints import initialize
from app.runtime.autonomous_activity.postgresql_serde import checkpoint_serde


class StrictReader:
    def __init__(self):
        self.serde=checkpoint_serde()
    def load(self,kind,value):
        if kind not in {'json','msgpack','bytes','null'}:raise ValueError('migration_checkpoint_type_unsupported')
        if value is not None and len(value)>16*1024*1024:raise ValueError('migration_checkpoint_value_too_large')
        blocked=[];unregister=register_serde_event_listener(blocked.append)
        try:result=self.serde.loads_typed((kind,value))
        finally:unregister()
        if blocked:raise ValueError('migration_checkpoint_object_unsupported')
        return result


def checkpoint_rows(db):
    return db.execute('SELECT thread_id,checkpoint_ns,checkpoint_id,parent_checkpoint_id,type,checkpoint,metadata FROM checkpoints ORDER BY thread_id,checkpoint_ns,checkpoint_id')


def digest_row(row):
    h=hashlib.sha256()
    for value in row:
        part=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
        h.update(len(part).to_bytes(8,'big'));h.update(part)
    return h.hexdigest()


def convert_checkpoints(migration):
    if migration.stage_done('checkpoints'):return
    initialize(migration.dsn)
    path=migration.source/'runtime/activity/activity-checkpoints.sqlite'
    if not path.exists():migration.mark('checkpoints');return
    reader=StrictReader()
    with source_db(path) as db,psycopg.connect(migration.dsn,autocommit=True,row_factory=dict_row) as pg:
        saver=PostgresSaver(pg,serde=reader.serde)
        for row in checkpoint_rows(db):
            thread,namespace,identifier,parent,kind,payload,raw_metadata=row
            digest=digest_row(row)
            prior=pg.execute('SELECT source_digest FROM pg_migration_checkpoints WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s',(thread,namespace,identifier)).fetchone()
            if prior:
                if prior['source_digest']!=digest:raise ValueError('migration_checkpoint_source_changed')
                continue
            checkpoint=reader.load(kind,payload);metadata=json.loads(raw_metadata) if raw_metadata else {}
            if checkpoint.get('id')!=identifier or checkpoint.get('v') not in {1,2,3,4}:raise ValueError('migration_checkpoint_version_unsupported')
            config={'configurable':{'thread_id':thread,'checkpoint_ns':namespace,'checkpoint_id':parent}}
            with pg.transaction():
                saver.put(config,checkpoint,metadata,checkpoint['channel_versions'])
                # Keep historical metadata, including deprecated SDK keys.
                pg.execute('UPDATE checkpoints SET metadata=%s WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s',(Jsonb(metadata),thread,namespace,identifier))
                pg.execute('INSERT INTO pg_migration_checkpoints VALUES(%s,%s,%s,%s)',(thread,namespace,identifier,digest))
        # Pending writes may exist before their checkpoint is durable. Preserve
        # these too; exact task/index keys prevent replay from shifting indices.
        with pg.transaction():
            for row in db.execute('SELECT thread_id,checkpoint_ns,checkpoint_id,task_id,task_path,idx,channel,type,value FROM writes ORDER BY thread_id,checkpoint_ns,checkpoint_id,task_id,idx'):
                reader.load(row[7],row[8])
                pg.execute('''INSERT INTO checkpoint_writes(thread_id,checkpoint_ns,checkpoint_id,task_id,task_path,idx,channel,type,blob)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(thread_id,checkpoint_ns,checkpoint_id,task_id,idx) DO NOTHING''',row)
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='angmoo_erased_checkpoint_threads'").fetchone():
                for (thread,) in db.execute('SELECT thread_id FROM angmoo_erased_checkpoint_threads'):
                    if pg.execute('SELECT 1 FROM checkpoints WHERE thread_id=%s UNION ALL SELECT 1 FROM checkpoint_writes WHERE thread_id=%s LIMIT 1',(thread,thread)).fetchone():
                        raise ValueError('migration_erased_checkpoint_contains_data')
                    pg.execute('INSERT INTO pg_checkpoint_threads VALUES(%s,true) ON CONFLICT(thread_id) DO UPDATE SET erased=true',(thread,))
    migration.mark('checkpoints')


def verify_checkpoints(migration):
    path=migration.source/'runtime/activity/activity-checkpoints.sqlite'
    if not path.exists():return {'checkpoints':0,'writes':0}
    reader=StrictReader();count=writes=0;digest=hashlib.sha256()
    with source_db(path) as db,psycopg.connect(migration.dsn,autocommit=True,row_factory=dict_row) as pg:
        saver=PostgresSaver(pg,serde=reader.serde)
        for row in checkpoint_rows(db):
            thread,namespace,identifier,parent,kind,payload,raw_metadata=row
            expected=reader.load(kind,payload);metadata=json.loads(raw_metadata) if raw_metadata else {}
            actual=saver.get_tuple({'configurable':{'thread_id':thread,'checkpoint_ns':namespace,'checkpoint_id':identifier}})
            actual_parent=actual.parent_config['configurable']['checkpoint_id'] if actual and actual.parent_config else None
            if actual is None or actual_parent!=parent or actual.checkpoint!=expected or actual.metadata!=metadata:
                raise ValueError('migration_checkpoint_roundtrip_mismatch')
            digest.update(digest_row(row).encode());count+=1
        for row in db.execute('SELECT thread_id,checkpoint_ns,checkpoint_id,task_id,task_path,idx,channel,type,value FROM writes ORDER BY thread_id,checkpoint_ns,checkpoint_id,task_id,idx'):
            actual=pg.execute('''SELECT task_path,channel,type,blob FROM checkpoint_writes WHERE thread_id=%s AND checkpoint_ns=%s
                AND checkpoint_id=%s AND task_id=%s AND idx=%s''',(row[0],row[1],row[2],row[3],row[5])).fetchone()
            if actual is None or (actual['task_path'],actual['channel'],actual['type'],bytes(actual['blob']))!=(row[4],row[6],row[7],row[8]):
                raise ValueError('migration_checkpoint_writes_mismatch')
            digest.update(digest_row(row).encode());writes+=1
        if pg.execute('SELECT count(*) AS n FROM checkpoints').fetchone()['n']!=count:raise ValueError('migration_checkpoint_count_mismatch')
        if pg.execute('SELECT count(*) AS n FROM checkpoint_writes').fetchone()['n']!=writes:raise ValueError('migration_checkpoint_write_count_mismatch')
    return {'checkpoints':count,'writes':writes,'roundtrip_digest':digest.hexdigest(),'strict_deserialization':True}
