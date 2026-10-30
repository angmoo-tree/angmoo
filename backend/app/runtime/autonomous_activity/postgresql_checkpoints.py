"""PostgreSQL activity checkpoints, pending writes and durable erasure fences."""
import asyncio,os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.postgres.base import MIGRATIONS
from langgraph.checkpoint.postgres import _ainternal
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from app.runtime.autonomous_activity.postgresql_serde import checkpoint_serde
from app.core.postgresql_capacity import CHECKPOINT_POOL_MAX
from app.core.postgresql_connections import serving_connection

TABLES=('checkpoints','checkpoint_blobs','checkpoint_writes')
from app.runtime.checkpoint_registry import _key, register, bound_store, unregister










def initialize(dsn):
    """Explicit schema owner operation, never an implicit fallback to SQLite."""
    with psycopg.connect(dsn,autocommit=True,row_factory=dict_row,connect_timeout=5) as conn:
        conn.execute('SELECT pg_advisory_lock(7402219)')
        try:
            PostgresSaver(conn).setup()
            with conn.transaction():
                conn.execute('''CREATE TABLE IF NOT EXISTS pg_checkpoint_threads(thread_id text PRIMARY KEY,erased boolean NOT NULL DEFAULT false);
                    CREATE TABLE IF NOT EXISTS pg_checkpoint_contract(singleton boolean PRIMARY KEY CHECK(singleton),version int NOT NULL);
                    CREATE OR REPLACE FUNCTION angmoo_checkpoint_fence() RETURNS trigger LANGUAGE plpgsql AS $$
                    DECLARE closed boolean; BEGIN
                    INSERT INTO pg_checkpoint_threads(thread_id) VALUES(NEW.thread_id) ON CONFLICT DO NOTHING;
                    SELECT erased INTO closed FROM pg_checkpoint_threads WHERE thread_id=NEW.thread_id FOR SHARE;
                    IF closed THEN RAISE EXCEPTION 'world_deleting' USING ERRCODE='23514'; END IF;
                    IF TG_OP='UPDATE' AND OLD.thread_id IS DISTINCT FROM NEW.thread_id THEN
                      SELECT erased INTO closed FROM pg_checkpoint_threads WHERE thread_id=OLD.thread_id FOR SHARE;
                      IF closed THEN RAISE EXCEPTION 'world_deleting' USING ERRCODE='23514'; END IF;
                    END IF;
                    RETURN NEW; END $$;''')
                for table in TABLES:
                    conn.execute(f'DROP TRIGGER IF EXISTS angmoo_checkpoint_fence ON {table}')
                    conn.execute(f'CREATE TRIGGER angmoo_checkpoint_fence BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION angmoo_checkpoint_fence()')
                conn.execute('INSERT INTO pg_checkpoint_contract VALUES(true,1) ON CONFLICT DO NOTHING')
                if conn.execute('SELECT version FROM pg_checkpoint_contract').fetchone()['version']!=1:
                    raise ValueError('postgresql_checkpoint_schema_mismatch')
        finally:conn.execute('SELECT pg_advisory_unlock(7402219)')


class FencedAsyncPostgresSaver(AsyncPostgresSaver):
    @asynccontextmanager
    async def _cursor(self,*,pipeline=False):
        # Explicit transactions cover all blob/checkpoint/writes in an SDK
        # operation, regardless of the installed libpq's pipeline capability.
        async with self.lock,_ainternal.get_connection(self.conn) as conn:
            if pipeline:
                async with conn.transaction(),conn.cursor(binary=True,row_factory=dict_row) as cur:
                    yield cur
            else:
                async with conn.cursor(binary=True,row_factory=dict_row) as cur:yield cur

    async def setup(self):
        async with self._cursor() as cur:
            await cur.execute('SELECT version FROM pg_checkpoint_contract WHERE singleton=true')
            row=await cur.fetchone()
            if row is None or row['version']!=1:raise ValueError('postgresql_checkpoint_schema_mismatch')
            await cur.execute('SELECT max(v) AS v FROM checkpoint_migrations')
            if (await cur.fetchone())['v']!=len(MIGRATIONS)-1:raise ValueError('postgresql_checkpoint_sdk_schema_mismatch')

    async def adelete_thread(self,thread_id):
        async with self._cursor(pipeline=True) as cur:
            await cur.execute('INSERT INTO pg_checkpoint_threads VALUES(%s,true) ON CONFLICT(thread_id) DO UPDATE SET erased=true',(thread_id,))
            for table in TABLES:await cur.execute(f'DELETE FROM {table} WHERE thread_id=%s',(thread_id,))

    async def rollback_pending(self):
        # Every owned cursor releases its explicit transaction before return.
        # There is no caller-owned transaction on the bounded shared pool.
        return None


class PostgresCheckpointStore:
    def __init__(self,dsn):
        self._dsn=dsn.replace('postgresql+psycopg://','postgresql://',1)
        self._pool=None;self._loop=None

    async def pool(self):
        loop=asyncio.get_running_loop()
        if self._pool is None:
            self._loop=loop
            self._pool=AsyncConnectionPool(self._dsn,min_size=0,max_size=CHECKPOINT_POOL_MAX,max_waiting=8,timeout=2,open=False,
                kwargs={'autocommit':True,'prepare_threshold':0,'row_factory':dict_row,'connect_timeout':5,'application_name':'angmoo-pg-checkpoints'})
            await self._pool.open()
        if self._loop is not loop:raise RuntimeError('postgresql_checkpoint_event_loop_changed')
        return self._pool

    @asynccontextmanager
    async def saver(self):
        saver=FencedAsyncPostgresSaver(await self.pool(),serde=checkpoint_serde())
        await saver.setup()
        yield saver

    async def close(self):
        if self._pool is not None:
            await self._pool.close();self._pool=None;self._loop=None

    def erase(self,activity_id):
        if not activity_id or len(activity_id)>100:raise ValueError('checkpoint_activity_identity_invalid')
        thread='activity:'+activity_id
        with serving_connection(self._dsn,connect_timeout=5) as conn:
            conn.execute('INSERT INTO pg_checkpoint_threads VALUES(%s,true) ON CONFLICT(thread_id) DO UPDATE SET erased=true',(thread,))
            for table in TABLES:conn.execute(f'DELETE FROM {table} WHERE thread_id=%s',(thread,))

    def result_basis(self,activity_id,lane,max_bytes):
        """Bound metadata/blob size before strictly deserializing a checkpoint."""
        serde=checkpoint_serde()
        try:
            with serving_connection(self._dsn,autocommit=True,row_factory=dict_row,connect_timeout=5) as conn:
                conn.execute("SET statement_timeout='1000ms'")
                with conn.transaction():
                    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    rows=conn.execute('''SELECT c.checkpoint_ns,c.checkpoint_id,octet_length(c.checkpoint::text)+
                        coalesce((SELECT sum(octet_length(b.blob)) FROM checkpoint_blobs b WHERE b.thread_id=c.thread_id AND b.checkpoint_ns=c.checkpoint_ns
                         AND b.version=c.checkpoint->'channel_versions'->>b.channel),0)+
                        coalesce((SELECT sum(octet_length(w.blob)) FROM checkpoint_writes w WHERE w.thread_id=c.thread_id
                         AND w.checkpoint_ns=c.checkpoint_ns AND w.checkpoint_id=c.checkpoint_id),0) AS size
                        FROM checkpoints c WHERE thread_id=%s AND checkpoint_ns LIKE %s ORDER BY checkpoint_id DESC LIMIT 256''',
                        ('activity:'+activity_id,'%'+lane.capitalize()+'ActivityGraph:%')).fetchall()
                    saver=PostgresSaver(conn,serde=serde)
                    for row in rows:
                        if row['size']>max_bytes:continue
                        item=saver.get_tuple({'configurable':{'thread_id':'activity:'+activity_id,'checkpoint_ns':row['checkpoint_ns'],'checkpoint_id':row['checkpoint_id']}})
                        if item is not None:yield item.checkpoint
        except Exception:
            raise ValueError('situation_result_basis_missing') from None
