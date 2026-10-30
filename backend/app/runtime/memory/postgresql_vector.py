"""pgvector exact cosine projection; canonical revalidation stays upstream."""
from contextlib import contextmanager
from contextvars import ContextVar
import json,struct
from threading import Event
from time import monotonic
from sqlalchemy import text
from app.core.postgresql_world_fence import fence_world
from sqlalchemy.exc import DBAPIError
from app.core.postgresql_deadline import read_deadline
from app.core.postgresql_reads import read_transaction
from app.domains.memory.contracts.vector_projection import MemoryVectorHit,MemoryVectorSearchResult
from app.runtime.memory.sqlite_vec1 import vector_blob,MemoryVectorProjectionError


class PostgresSearchCancellation:
    def __init__(self,deadline):
        self.deadline=deadline
        self.signal=Event()
    def cancel(self):self.signal.set()
    def expired(self):return self.signal.is_set() or monotonic()>=self.deadline


def encoded_vector(values):
    # Retain Vec1's validated float32 representation, not fresh embeddings.
    return json.dumps(struct.unpack('=768f',vector_blob(values)),separators=(',',':'))




class PostgresMemoryVectorIndex:
    provider='postgresql'
    schema_revision='pgvector-exact-768-cos-v1'

    def __init__(self,engine,*,generation='v1'):
        self.engine,self.generation=engine,generation
        self._effect=ContextVar(f'pg_vector_effect_{id(self)}',default=None)

    @contextmanager
    def _connection(self,*,cancellation=None):
        current=self._effect.get()
        if current is not None:
            yield current
            return
        try:
            with self.engine.begin() as c:
                c.exec_driver_sql("SET LOCAL lock_timeout='50ms'")
                if cancellation is not None:
                    with read_deadline(c,cancellation.deadline,cancelled=cancellation.signal):yield c
                else:yield c
        except DBAPIError as exc:
            error=MemoryVectorProjectionError('memory_vector_database_error')
            error.sqlstate=getattr(exc.orig,'sqlstate',None)
            raise error from None
        except TimeoutError:
            raise MemoryVectorProjectionError('memory_vector_cancelled') from None

    @contextmanager
    def effect_connection(self):
        with self._connection() as c:
            token=self._effect.set(c)
            try:yield
            finally:self._effect.reset(token)

    def open(self):
        with self._connection() as c:
            version=c.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar_one()
            prepared=c.execute(text("SELECT to_regclass('pg_memory_vectors') IS NOT NULL AND to_regclass('pg_memory_vector_generations') IS NOT NULL AND to_regclass('pg_memory_vector_scope') IS NOT NULL AND to_regclass('pg_memory_vector_item') IS NOT NULL")).scalar_one()
            if not prepared:c.exec_driver_sql("""CREATE TABLE IF NOT EXISTS pg_memory_vector_generations(
                generation text PRIMARY KEY,revision text NOT NULL,phase text NOT NULL DEFAULT 'active');
                CREATE TABLE IF NOT EXISTS pg_memory_vectors(
                generation text NOT NULL REFERENCES pg_memory_vector_generations(generation),
                document_id text NOT NULL,memory_item_id text NOT NULL,version int NOT NULL CHECK(version>0),
                content_hash text NOT NULL CHECK(length(content_hash)=64),profile text NOT NULL,
                owner_id text NOT NULL,world_id text NOT NULL,subject_id text NOT NULL,
                occurred_at double precision NOT NULL,counterpart_id text,thread_id text,
                embedding vector(768) NOT NULL,PRIMARY KEY(generation,document_id));
                CREATE INDEX IF NOT EXISTS pg_memory_vector_scope ON pg_memory_vectors(generation,owner_id,world_id,subject_id,profile);
                CREATE INDEX IF NOT EXISTS pg_memory_vector_item ON pg_memory_vectors(memory_item_id);""")
            c.execute(text('INSERT INTO pg_memory_vector_generations(generation,revision) VALUES(:g,:r) ON CONFLICT DO NOTHING'),{'g':self.generation,'r':self.schema_revision})
            revision=c.execute(text('SELECT revision FROM pg_memory_vector_generations WHERE generation=:g'),{'g':self.generation}).scalar_one()
            if revision!=self.schema_revision:raise MemoryVectorProjectionError('memory_vector_profile_mismatch')
            # Approximate indexes are deliberately absent from this experiment.
            if c.execute(text("SELECT 1 FROM pg_indexes WHERE tablename='pg_memory_vectors' AND (indexdef LIKE '%USING hnsw%' OR indexdef LIKE '%USING ivfflat%')")).first():
                raise MemoryVectorProjectionError('memory_vector_index_mode_mismatch')
        return 'pgvector '+version+' exact cosine 768'

    def require_budget_receipt(self):
        with self._connection() as c:
            value=c.execute(text('SELECT source_budget_state FROM pg_vector_state WHERE singleton=true')).scalar_one()
            if value not in {'fresh','migrated-v41'}:raise MemoryVectorProjectionError('memory_vector_legacy_budget_missing')

    def check_writable(self):
        with self._connection() as c:
            c.exec_driver_sql("SET LOCAL lock_timeout='25ms'")
            c.exec_driver_sql('LOCK TABLE pg_memory_vectors IN ROW EXCLUSIVE MODE')

    def upsert(self,documents):
        prepared=[]
        for d in documents:
            encoded=encoded_vector(d.vector)
            if d.version<1 or not d.profile or len(d.content_hash)!=64 or not d.document_id or d.occurred_at.tzinfo is None:
                raise ValueError('memory_vector_document_invalid')
            prepared.append(dict(g=self.generation,id=d.document_id,item=d.memory_item_id,v=d.version,h=d.content_hash,p=d.profile,
                owner=d.scope.owner_id,world=d.scope.world_id,subject=d.scope.subject_world_character_id,
                at=d.occurred_at.timestamp(),counterpart=d.counterpart_world_character_id,thread=d.thread_id,embedding=encoded))
        with self._connection() as c:
            for world in sorted({v['world'] for v in prepared}):fence_world(c,world)
            for v in prepared:
                c.execute(text('''INSERT INTO pg_memory_vectors VALUES(:g,:id,:item,:v,:h,:p,:owner,:world,:subject,:at,:counterpart,:thread,CAST(:embedding AS vector(768)))
                    ON CONFLICT(generation,document_id) DO UPDATE SET memory_item_id=excluded.memory_item_id,version=excluded.version,
                    content_hash=excluded.content_hash,profile=excluded.profile,owner_id=excluded.owner_id,world_id=excluded.world_id,
                    subject_id=excluded.subject_id,occurred_at=excluded.occurred_at,counterpart_id=excluded.counterpart_id,
                    thread_id=excluded.thread_id,embedding=excluded.embedding WHERE pg_memory_vectors.version<=excluded.version'''),v)

    def identity(self,document_id):
        with self._connection() as c:
            row=c.execute(text('SELECT version,content_hash,profile FROM pg_memory_vectors WHERE generation=:g AND document_id=:id'),{'g':self.generation,'id':document_id}).first()
            return tuple(row) if row else None

    def matches(self,d):
        with self._connection() as c:
            row=c.execute(text('SELECT version,content_hash,profile,owner_id,world_id,subject_id,occurred_at,counterpart_id,thread_id FROM pg_memory_vectors WHERE generation=:g AND document_id=:id'),{'g':self.generation,'id':d.document_id}).first()
            return row is not None and tuple(row)==(d.version,d.content_hash,d.profile,d.scope.owner_id,d.scope.world_id,d.scope.subject_world_character_id,d.occurred_at.timestamp(),d.counterpart_world_character_id,d.thread_id)

    def delete(self,document_id):
        with self._connection() as c:c.execute(text('DELETE FROM pg_memory_vectors WHERE generation=:g AND document_id=:id'),{'g':self.generation,'id':document_id})

    def erase_items(self,identifiers):
        with self._connection() as c:
            # Privacy erasure includes every retained/rebuild generation.
            for item in identifiers:
                c.execute(text('DELETE FROM pg_memory_vectors WHERE memory_item_id=:item'),{'item':item})

    def refresh_version(self,document_id,*,content_hash,version,scope=None,occurred_at=None,counterpart_world_character_id=None,thread_id=None):
        if scope is not None and (occurred_at is None or occurred_at.tzinfo is None):raise ValueError('memory_vector_metadata_invalid')
        values=dict(id=document_id,g=self.generation,h=content_hash,v=version)
        updates='version=:v'
        with self._connection() as c:
            if scope is not None:
                fence_world(c,scope.world_id)
                updates+=',owner_id=:owner,world_id=:world,subject_id=:subject,occurred_at=:at,counterpart_id=:counterpart,thread_id=:thread'
                values.update(owner=scope.owner_id,world=scope.world_id,subject=scope.subject_world_character_id,at=occurred_at.timestamp(),counterpart=counterpart_world_character_id,thread=thread_id)
            c.execute(text(f'UPDATE pg_memory_vectors SET {updates} WHERE generation=:g AND document_id=:id AND content_hash=:h AND version<=:v'),values)

    def document_upper_bound(self):
        with self._connection() as c:return c.execute(text('SELECT max(document_id) FROM pg_memory_vectors WHERE generation=:g'),{'g':self.generation}).scalar_one() or ''

    def document_page(self,*,after='',limit=64):
        if not 1<=limit<=256:raise ValueError('memory_vector_page_limit')
        with self._connection() as c:
            return tuple(tuple(r) for r in c.execute(text('SELECT document_id,memory_item_id FROM pg_memory_vectors WHERE generation=:g AND document_id>:a ORDER BY document_id LIMIT :n'),{'g':self.generation,'a':after,'n':limit}))

    def search(self,query,*,cancellation):
        started=monotonic();embedding=encoded_vector(query.vector)
        values=dict(g=self.generation,owner=query.scope.owner_id,world=query.scope.world_id,subject=query.scope.subject_world_character_id,profile=query.profile,embedding=embedding,n=query.limit)
        clauses=['generation=:g','owner_id=:owner','world_id=:world','subject_id=:subject','profile=:profile']
        for clause,key,value in [('occurred_at>=:from_at','from_at',None if query.occurred_from is None else query.occurred_from.timestamp()),
            ('occurred_at<:to_at','to_at',None if query.occurred_to is None else query.occurred_to.timestamp()),
            ('counterpart_id=:counterpart','counterpart',query.counterpart_world_character_id),('thread_id=:thread','thread',query.thread_id)]:
            if value is not None:clauses.append(clause);values[key]=value
        if query.allowed_thread_ids is not None:
            clauses.append('(thread_id IS NULL OR thread_id=ANY(:allowed_threads))')
            values['allowed_threads']=list(query.allowed_thread_ids)
        where=' AND '.join(clauses)
        def read(c):
            count=c.execute(text('SELECT count(*) FROM pg_memory_vectors WHERE '+where),values).scalar_one()
            rows=c.execute(text('SELECT document_id,memory_item_id,version,content_hash,embedding <=> CAST(:embedding AS vector(768)) AS distance FROM pg_memory_vectors WHERE '+where+' ORDER BY distance,document_id LIMIT :n'),values).all()
            if cancellation.expired():raise MemoryVectorProjectionError('memory_vector_cancelled')
            return count,rows
        try:
            current=self._effect.get()
            if current is not None:
                # A caller-owned write unit owns its own atomic retry policy.
                count,rows=read(current)
            else:
                count,rows=read_transaction(self.engine,read,
                    deadline=cancellation.deadline,cancelled=cancellation.signal)
        except DBAPIError as exc:
            error=MemoryVectorProjectionError('memory_vector_database_error')
            error.sqlstate=getattr(exc.orig,'sqlstate',None)
            raise error from None
        except TimeoutError:
            raise MemoryVectorProjectionError('memory_vector_cancelled') from None
        return MemoryVectorSearchResult(tuple(MemoryVectorHit(*r) for r in rows),count,self.generation,(monotonic()-started)*1000)
