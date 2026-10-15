"""Incremental, restartable projection from accepted summary registrations."""
import asyncio
from datetime import UTC, datetime
from time import time

from app.domains.memory.repository.vector_work import eligible_page, retained_registration
from app.runtime.memory.recall_composition import recall_document_source


class MemoryVectorProjection:
    def __init__(self, session_factory, index, *, provider=None, on_clean_cycle=None, episode_only=False):
        self._factory, self.index = session_factory, index
        self._source = recall_document_source(session_factory, episode_only=episode_only)
        self._provider = provider
        from app.runtime.received_results import result_journal
        self.journal = result_journal("memory-embedding")
        self._received = {}
        self.last_usage = None
        self._cursor = self._cleanup_cursor = ""
        self._task = None
        self._closing = False
        self.status = "stopped"
        self.last_code = None
        self.logical_calls = self.physical_attempts = 0
        # Per-content failures survive the process in the disposable projection.
        self._attempts_ready = False
        self._on_clean_cycle = on_clean_cycle
        self._cycle_clean = True
        self._eligible_clean = self._cleanup_complete = False
        self._tick_failed = False
        from app.runtime.memory.canonical_work import MemoryCanonicalWork
        self._canonical = MemoryCanonicalWork()

    def _prepare_attempts(self):
        if self._attempts_ready:
            return
        with self.index._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS embedding_attempts_v2 (document_id TEXT NOT NULL, profile TEXT NOT NULL, content_hash TEXT NOT NULL, credential_revision TEXT NOT NULL, attempts INTEGER NOT NULL, code TEXT, retry_after REAL NOT NULL, PRIMARY KEY(document_id,profile,content_hash,credential_revision))")
            connection.commit()
        self._attempts_ready = True

    def _claim_attempt(self, doc_id, profile, digest, credential_revision):
        return doc_id in self._claim_attempts(((doc_id, profile, digest, credential_revision),))

    def _claim_attempts(self, keys):
        """Admit a physical request atomically; local contention spends no keys."""
        self._prepare_attempts()
        with self.index._connect() as connection:
            connection.execute("PRAGMA busy_timeout=50")
            connection.execute("BEGIN IMMEDIATE")
            admitted = set()
            for key in keys:
                old = connection.execute("SELECT attempts,code,retry_after FROM embedding_attempts_v2 WHERE document_id=? AND profile=? AND content_hash=? AND credential_revision=?", key).fetchone()
                if old and (old[0] >= 3 or old[1] == "terminal" or old[2] > time()):
                    continue
                count = old[0] + 1 if old else 1
                connection.execute("INSERT INTO embedding_attempts_v2 VALUES(?,?,?,?,?,NULL,?) ON CONFLICT(document_id,profile,content_hash,credential_revision) DO UPDATE SET attempts=excluded.attempts,code=NULL,retry_after=excluded.retry_after", (*key, count, time() + 30 * 2 ** (count - 1)))
                admitted.add(key[0])
            connection.commit()
        return admitted

    def _finish_attempt(self, doc_id, profile, digest, credential_revision, *, terminal):
        with self.index._connect() as connection:
            if terminal:
                connection.execute("UPDATE embedding_attempts_v2 SET code='terminal' WHERE document_id=? AND profile=? AND content_hash=? AND credential_revision=?", (doc_id, profile, digest, credential_revision))
            else:
                connection.execute("DELETE FROM embedding_attempts_v2 WHERE document_id=? AND profile=? AND content_hash=?", (doc_id, profile, digest))
            connection.commit()

    async def sync_item(self, item_id, *, credential_revision=None):
        result = await self.sync_items((item_id,), credential_revision=credential_revision)
        return result[item_id]

    async def sync_items(self, item_ids, *, credential_revision=None):
        from app.runtime.memory.vector_batches import sync_items
        return await sync_items(self, item_ids, credential_revision=credential_revision)

    async def tick(self):
        await self._prepare_page()
        self._tick_failed = False
        if not self._cursor:
            self._eligible_clean = False
        with self._factory() as session:
            ids = eligible_page(session, after=self._cursor)
        outcomes = await self.sync_items(ids)
        for item_id in ids:
            outcome = outcomes[item_id]
            if outcome not in {"indexed", "current", "disabled", "ineligible", "source_unavailable"}:
                self._cycle_clean = False
                self._eligible_clean = False
                self._tick_failed = True
            self._cursor = item_id
            await asyncio.sleep(0)
        if len(ids) < 64:
            self._cursor = ""
        rows = self.index.document_page(after=self._cleanup_cursor)
        for doc_id, item_id in rows:
            with self._factory() as session:
                eligible = retained_registration(session, item_id)
            if not eligible:
                self.index.delete(doc_id)
            self._cleanup_cursor = doc_id
        if len(rows) < 64:
            self._cleanup_cursor = ""
            self._cleanup_complete = True
        if len(ids) < 64:
            self._eligible_clean = self._cycle_clean
            self._cycle_clean = True
        if self._eligible_clean and self._cleanup_complete and self._on_clean_cycle is not None:
            self._on_clean_cycle(self.index)
            self._on_clean_cycle = None

    async def _prepare_page(self):
        from app.runtime.memory.vector_preparation import prepare_page
        await prepare_page(self)

    async def start(self):
        self._closing = False
        if self._canonical.closed:
            from app.runtime.memory.canonical_work import MemoryCanonicalWork
            self._canonical = MemoryCanonicalWork()
        self.index.open()
        self.status = "ready"
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            try:
                await self.tick()
                self.status = "degraded" if self._tick_failed else "ready"
            except asyncio.CancelledError:
                raise
            except Exception:
                self.status, self.last_code = "degraded", "memory_vector_projection_failed"
            await asyncio.sleep(1)

    def fence(self):
        self._closing = True
        if self._task is not None:
            self._task.cancel()

    async def stop(self):
        self.fence()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self.status = "stopped"
        await self._canonical.drain()
        self._canonical.close()
