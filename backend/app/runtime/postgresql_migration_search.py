"""Preserve paid Vec1 payloads/budgets; rebuild disposable lexical indexes."""
import hashlib,json,struct,time
from datetime import UTC,datetime
from sqlalchemy import text
from app.database import create_session_factory
from app.runtime.postgresql_migration import source_db,add_digest,canonical_path
from app.runtime.memory.vector_resources import bundled_vector_index
from app.runtime.memory.postgresql_vector import PostgresMemoryVectorIndex,encoded_vector
from app.runtime.memory.postgresql_generations import initialize_state
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument


def sources(migration):
    return sorted((migration.source/'search/memory-vectors/generations').glob('*/vectors.sqlite3'))


def vector_rows(path):
    index=bundled_vector_index(path,generation=path.parent.name)
    with index._connect(read_only=True) as db:
        if db.execute('SELECT revision,generation FROM projection_profile').fetchall()!=[('memory-vec1-flat.v1',path.parent.name)]:
            raise ValueError('migration_vector_profile_mismatch')
        if db.execute('SELECT count(*) FROM documents').fetchone()[0]!=db.execute('SELECT count(*) FROM vectors').fetchone()[0]:
            raise ValueError('migration_vector_orphan')
        for row in db.execute('''SELECT d.document_id,d.memory_item_id,d.version,d.content_hash,v.owner_id,v.world_id,v.subject_id,
                v.profile,v.occurred_at,v.counterpart_id,v.thread_id,v.vector FROM documents d JOIN vectors v ON v.rowid=d.rowid ORDER BY d.document_id'''):
            if not isinstance(row[-1],bytes) or len(row[-1])!=3072:raise ValueError('migration_vector_payload_invalid')
            vector=struct.unpack('=768f',row[-1]);encoded_vector(vector)
            yield MemoryVectorDocument(row[0],row[1],MemoryScope(row[4],row[5],row[6]),row[2],row[3],row[7],
                vector,datetime.fromtimestamp(row[8],UTC),row[9],row[10])


def budget_rows(migration):
    # Disk-backed merge keeps memory bounded even for long-lived installations.
    import sqlite3
    expected=migration.work/'budget-expected.sqlite'
    with sqlite3.connect(expected) as merged:
        merged.execute('CREATE TABLE IF NOT EXISTS budgets(item_id text,profile text,content_hash text,credential_revision text,attempts integer,code text,retry_after real,PRIMARY KEY(item_id,profile,content_hash,credential_revision))')
        merged.execute('DELETE FROM budgets')
        with source_db(canonical_path(migration.source)) as canonical:
            for row in canonical.execute('SELECT item_id,profile,content_hash,credential_revision,attempts,code,retry_after FROM memory_vector_attempts'):
                merged.execute('INSERT INTO budgets VALUES(?,?,?,?,?,?,?)',row)
        for path in sources(migration):
            with source_db(path) as db:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE name='embedding_attempts_v2'").fetchone():continue
                for identifier,profile,digest,revision,attempts,code,due in db.execute('SELECT document_id,profile,content_hash,credential_revision,attempts,code,retry_after FROM embedding_attempts_v2'):
                    merged.execute('''INSERT INTO budgets VALUES(?,?,?,?,?,?,?) ON CONFLICT DO UPDATE SET
                        attempts=max(budgets.attempts,excluded.attempts),retry_after=max(budgets.retry_after,excluded.retry_after),
                        code=CASE WHEN budgets.code='terminal' OR excluded.code='terminal' THEN 'terminal' ELSE coalesce(budgets.code,excluded.code) END''',
                        (identifier.removeprefix('memory-item:'),profile,digest,revision,attempts,code,due))
        merged.commit()
        yield from merged.execute('SELECT * FROM budgets ORDER BY item_id,profile,content_hash,credential_revision')


def convert_vectors(migration):
    if migration.stage_done('vectors'):return
    PostgresMemoryVectorIndex(migration.engine,generation='v1').open()
    for path in sources(migration):
        index=PostgresMemoryVectorIndex(migration.engine,generation=path.parent.name);index.open()
        batch=[]
        for document in vector_rows(path):
            batch.append(document)
            if len(batch)==64:index.upsert(tuple(batch));batch.clear()
        if batch:index.upsert(tuple(batch))
    with migration.engine.begin() as c:
        for item,profile,digest,revision,attempts,code,due in budget_rows(migration):
            c.execute(text('''INSERT INTO memory_vector_attempts VALUES(:i,:p,:d,:r,:a,:c,:t) ON CONFLICT(item_id,profile,content_hash,credential_revision)
                DO UPDATE SET attempts=greatest(memory_vector_attempts.attempts,excluded.attempts),
                retry_after=greatest(memory_vector_attempts.retry_after,excluded.retry_after),
                code=CASE WHEN memory_vector_attempts.code='terminal' OR excluded.code='terminal' THEN 'terminal'
                     ELSE coalesce(memory_vector_attempts.code,excluded.code) END'''),dict(i=item,p=profile,d=digest,r=revision,a=attempts,c=code,t=due))
    initialize_state(migration.engine,budget_state='migrated-v41')
    marker=migration.source/'search/memory-vectors/current.json'
    state=json.loads(marker.read_text()) if marker.exists() else {'version':1,'active':'v1','staging':None,'previous':None}
    if state.get('version')!=1:raise ValueError('migration_vector_generation_unsupported')
    with migration.engine.begin() as c:
        c.execute(text('UPDATE pg_vector_state SET active=:active,staging=:staging,previous=:previous WHERE singleton=true'),
            {k:state.get(k) for k in ('active','staging','previous')})
    migration.mark('vectors')


def verify_vectors(migration):
    count=stale=0;digest=hashlib.sha256()
    with migration.engine.connect() as c:
        for path in sources(migration):
            for d in vector_rows(path):
                row=c.execute(text('''SELECT memory_item_id,version,content_hash,profile,owner_id,world_id,subject_id,occurred_at,
                    counterpart_id,thread_id,embedding::text FROM pg_memory_vectors WHERE generation=:g AND document_id=:d'''),{'g':path.parent.name,'d':d.document_id}).one()
                expected=(d.memory_item_id,d.version,d.content_hash,d.profile,d.scope.owner_id,d.scope.world_id,d.scope.subject_world_character_id,
                    d.occurred_at.timestamp(),d.counterpart_world_character_id,d.thread_id)
                # Text output must round-trip to the same float32 bytes.
                if tuple(row[:-1])!=expected or struct.pack('=768f',*json.loads(row[-1]))!=struct.pack('=768f',*d.vector):
                    raise ValueError('migration_vector_value_mismatch')
                add_digest(digest,(path.parent.name,d.document_id,*expected,struct.pack('=768f',*d.vector)))
                canonical=c.execute(text('SELECT version,deleted_at FROM memory_items WHERE id=:i'),{'i':d.memory_item_id}).first()
                if canonical is None:raise ValueError('migration_vector_canonical_missing')
                if canonical.version!=d.version or canonical.deleted_at is not None:stale+=1
                count+=1
        actual=c.execute(text('SELECT count(*) FROM pg_memory_vectors')).scalar_one()
        if actual!=count:raise ValueError('migration_vector_count_mismatch')
    return {'count':count,'float32_digest':digest.hexdigest(),'preexisting_stale_registrations':stale,'new_embedding_calls':0,'search':'exact_cosine_768'}


def rebuild_search(migration):
    if migration.stage_done('search'):return
    from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
    from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings
    from app.runtime.memory.recall_projection import EmbeddedMemoryRecallProjection
    from app.runtime.search.postgresql_fts import PostgresFtsSearchIndex
    index=PostgresMemoryRecallIndex(migration.engine,settings=MemoryRecallIndexSettings.for_representation('episode_v1'))
    projection=EmbeddedMemoryRecallProjection(index=index,session_factory=create_session_factory(migration.engine),episode_only=True)
    try:
        projection.start(background=False);deadline=time.monotonic()+300
        while not projection.is_caught_up and time.monotonic()<deadline:
            projection.advance_rebuild(max_pages=3)
            if projection.state.value=='degraded':raise ValueError('migration_recall_rebuild_failed')
        if not projection.is_caught_up or not index.doctor().healthy:raise ValueError('migration_recall_rebuild_incomplete')
        social=PostgresFtsSearchIndex(migration.engine);social.open()
        # Current product retires SNS FTS at startup; preserve the old adapter's
        # implementation, but do not invent a live recommendation dependency.
        if not social.doctor().healthy:raise ValueError('migration_social_search_unhealthy')
    finally:projection.stop()
    migration.mark('search')
